using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace ASUMuseum.ConversationalAgent
{
    /// <summary>
    /// Persists across scene loads and owns the backend session id. Calls
    /// /session/start lazily on first use.
    /// </summary>
    public class SessionState : MonoBehaviour
    {
        public static SessionState Instance { get; private set; }

        [SerializeField] private string backendBaseUrl = "http://localhost:8000";
        [SerializeField] private string language = "en";

        public string SessionId { get; private set; }
        public string Language => language;
        public List<string> VisitedArtworks { get; } = new List<string>();
        public bool IsReady => !string.IsNullOrEmpty(SessionId);

        public string BackendBaseUrl
        {
            get => backendBaseUrl;
            set => backendBaseUrl = value;
        }

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }

        public IEnumerator EnsureSession(Action<string> onReady = null, Action<string> onError = null)
        {
            if (IsReady)
            {
                onReady?.Invoke(SessionId);
                yield break;
            }

            string url = $"{backendBaseUrl.TrimEnd('/')}/session/start";
            string body = JsonUtility.ToJson(new StartRequest { language = language });

            using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
            {
                req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");

                yield return req.SendWebRequest();

                if (req.result != UnityWebRequest.Result.Success)
                {
                    onError?.Invoke(req.error);
                    yield break;
                }

                var resp = JsonUtility.FromJson<StartResponse>(req.downloadHandler.text);
                SessionId = resp.session_id;
                onReady?.Invoke(SessionId);
            }
        }

        public void RecordVisit(string artworkId)
        {
            if (!string.IsNullOrEmpty(artworkId) && !VisitedArtworks.Contains(artworkId))
            {
                VisitedArtworks.Add(artworkId);
            }
        }

        [Serializable]
        private class StartRequest { public string language; }

        [Serializable]
        private class StartResponse { public string session_id; }
    }
}
