using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.Networking;

namespace ASUMuseum.ConversationalAgent
{
    /// <summary>
    /// Orchestrates a single push-to-talk turn:
    ///   1. record voice
    ///   2. POST /transcribe
    ///   3. POST /query (with current ArtworkContext + visited list)
    ///   4. play returned audio_url through AgentAudioPlayer
    ///
    /// Network calls go through UnityWebRequest wrapped in coroutines (no UniTask
    /// dependency assumed). The single network-touching file in the package, by design.
    /// </summary>
    public class ConversationalAgent : MonoBehaviour
    {
        [Header("Backend")]
        [SerializeField] private string backendBaseUrl = "http://localhost:8000";

        [Header("Wiring")]
        [SerializeField] private SessionState session;
        [SerializeField] private VoiceCapture voiceCapture;
        [SerializeField] private AgentAudioPlayer audioPlayer;

        [Header("UX")]
        [Tooltip("Seconds the UI should display a thinking indicator before assuming the request is slow.")]
        [SerializeField] private float thinkingIndicatorDuration = 0.5f;

        public UnityEvent OnThinkingStarted = new UnityEvent();
        public UnityEvent OnThinkingEnded = new UnityEvent();
        public UnityEvent<string> OnTranscriptReady = new UnityEvent<string>();
        public UnityEvent<string> OnResponseReady = new UnityEvent<string>();
        public UnityEvent<string> OnError = new UnityEvent<string>();

        public string BackendBaseUrl
        {
            get => backendBaseUrl;
            set => backendBaseUrl = value;
        }

        public float ThinkingIndicatorDuration => thinkingIndicatorDuration;

        private bool _inFlight;

        public void OnPushToTalkPressed()
        {
            if (_inFlight) return;
            if (voiceCapture != null) voiceCapture.StartRecording();
        }

        public void OnPushToTalkReleased()
        {
            if (_inFlight || voiceCapture == null) return;
            byte[] audio = voiceCapture.StopRecording();
            if (audio == null || audio.Length == 0) return;
            StartCoroutine(SendQueryRoutine(audio));
        }

        private IEnumerator SendQueryRoutine(byte[] audioWav)
        {
            _inFlight = true;
            OnThinkingStarted.Invoke();
            float started = Time.realtimeSinceStartup;

            // 1. Make sure we have a session.
            if (session != null && !session.IsReady)
            {
                yield return session.EnsureSession(
                    onError: err => OnError.Invoke($"session/start failed: {err}"));
                if (!session.IsReady)
                {
                    EndTurn(started);
                    yield break;
                }
            }

            // 2. Transcribe.
            string transcript = null;
            yield return PostJson<TranscribeResponse>(
                "/transcribe",
                new TranscribeRequest
                {
                    audio_base64 = Convert.ToBase64String(audioWav),
                    language = session?.Language ?? "en",
                },
                ok => transcript = ok.transcript,
                err => OnError.Invoke($"/transcribe failed: {err}"));

            if (string.IsNullOrEmpty(transcript))
            {
                EndTurn(started);
                yield break;
            }
            OnTranscriptReady.Invoke(transcript);

            // 3. Query.
            var ctx = ArtworkContext.Current;
            var visited = session != null ? session.VisitedArtworks : new List<string>();
            QueryResponse response = null;
            yield return PostJson<QueryResponse>(
                "/query",
                new QueryRequest
                {
                    session_id = session?.SessionId ?? "",
                    artwork_id = ctx != null && ctx.IsValid ? ctx.ArtworkId : null,
                    query_text = transcript,
                    language = session?.Language ?? "en",
                    visited_artworks = visited.ToArray(),
                },
                ok => response = ok,
                err => OnError.Invoke($"/query failed: {err}"));

            if (response == null)
            {
                EndTurn(started);
                yield break;
            }

            if (ctx != null && ctx.IsValid && session != null)
            {
                session.RecordVisit(ctx.ArtworkId);
            }

            OnResponseReady.Invoke(response.response_text);

            // 4. Play audio (optional — falls back silently if missing).
            if (audioPlayer != null && !string.IsNullOrEmpty(response.audio_url))
            {
                string url = response.audio_url.StartsWith("http")
                    ? response.audio_url
                    : $"{backendBaseUrl.TrimEnd('/')}{response.audio_url}";
                yield return audioPlayer.PlayFromUrl(url);
            }

            EndTurn(started);
        }

        private void EndTurn(float startedAt)
        {
            _inFlight = false;
            // Honor the indicator duration so the UI doesn't flash on fast responses.
            float elapsed = Time.realtimeSinceStartup - startedAt;
            if (elapsed < thinkingIndicatorDuration)
            {
                StartCoroutine(DelayedThinkingEnd(thinkingIndicatorDuration - elapsed));
            }
            else
            {
                OnThinkingEnded.Invoke();
            }
        }

        private IEnumerator DelayedThinkingEnd(float wait)
        {
            yield return new WaitForSeconds(wait);
            OnThinkingEnded.Invoke();
        }

        private IEnumerator PostJson<TResp>(
            string path,
            object body,
            Action<TResp> onSuccess,
            Action<string> onError)
        {
            string url = $"{backendBaseUrl.TrimEnd('/')}{path}";
            string json = JsonUtility.ToJson(body);

            using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
            {
                req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");

                yield return req.SendWebRequest();

                if (req.result != UnityWebRequest.Result.Success)
                {
                    onError?.Invoke($"{req.responseCode} {req.error}");
                    yield break;
                }
                try
                {
                    var parsed = JsonUtility.FromJson<TResp>(req.downloadHandler.text);
                    onSuccess?.Invoke(parsed);
                }
                catch (Exception ex)
                {
                    onError?.Invoke($"parse error: {ex.Message}");
                }
            }
        }

        // --- DTOs (must be plain serializable types for JsonUtility) ---

        [Serializable]
        public class QueryRequest
        {
            public string session_id;
            public string artwork_id;
            public string query_text;
            public string language;
            public string[] visited_artworks;
        }

        [Serializable]
        public class QueryResponse
        {
            public string response_text;
            public string audio_url;
            public string session_id;
        }

        [Serializable]
        public class TranscribeRequest
        {
            public string audio_base64;
            public string language;
        }

        [Serializable]
        public class TranscribeResponse
        {
            public string transcript;
            public float confidence;
        }
    }
}
