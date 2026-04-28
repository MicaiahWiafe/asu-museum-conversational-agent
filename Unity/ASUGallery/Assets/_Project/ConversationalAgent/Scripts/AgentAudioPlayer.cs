using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

namespace ASUMuseum.ConversationalAgent
{
    /// <summary>
    /// Plays the agent response back at the artwork's anchor with HRTF spatialization.
    /// The AudioSource is created on a child GameObject so callers can re-parent the
    /// player to whatever anchor the artwork uses without disturbing other components.
    /// </summary>
    [RequireComponent(typeof(AudioSource))]
    public class AgentAudioPlayer : MonoBehaviour
    {
        private AudioSource _source;

        private void Awake()
        {
            _source = GetComponent<AudioSource>();
            _source.spatialBlend = 1f;
            _source.spatialize = true;
            _source.spatializePostEffects = true;
            _source.rolloffMode = AudioRolloffMode.Linear;
            _source.minDistance = 0.5f;
            _source.maxDistance = 6f;
            _source.playOnAwake = false;
        }

        public void AnchorTo(Transform anchor)
        {
            if (anchor == null) return;
            transform.SetParent(anchor, worldPositionStays: false);
            transform.localPosition = Vector3.zero;
        }

        public IEnumerator PlayFromUrl(string url)
        {
            if (string.IsNullOrEmpty(url)) yield break;

            using (var req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.MPEG))
            {
                yield return req.SendWebRequest();
                if (req.result != UnityWebRequest.Result.Success)
                {
                    Debug.LogWarning($"[AgentAudioPlayer] Failed to fetch audio: {req.error}");
                    yield break;
                }
                var clip = DownloadHandlerAudioClip.GetContent(req);
                _source.clip = clip;
                _source.Play();
            }
        }

        public void Stop()
        {
            if (_source != null && _source.isPlaying) _source.Stop();
        }
    }
}
