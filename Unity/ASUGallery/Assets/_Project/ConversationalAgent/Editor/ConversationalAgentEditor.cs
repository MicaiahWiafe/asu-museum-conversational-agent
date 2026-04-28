using UnityEditor;
using UnityEngine;
using UnityEngine.Networking;

namespace ASUMuseum.ConversationalAgent.Editor
{
    [CustomEditor(typeof(ConversationalAgent))]
    public class ConversationalAgentEditor : UnityEditor.Editor
    {
        private string _healthStatus = "(not tested)";

        public override void OnInspectorGUI()
        {
            DrawDefaultInspector();
            var agent = (ConversationalAgent)target;

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Backend Diagnostics", EditorStyles.boldLabel);

            EditorGUI.BeginDisabledGroup(true);
            EditorGUILayout.TextField(
                "Current Session Id",
                SessionState.Instance != null ? SessionState.Instance.SessionId ?? "" : "(no SessionState yet)");
            EditorGUI.EndDisabledGroup();

            EditorGUILayout.LabelField("Last /health probe", _healthStatus);

            if (GUILayout.Button("Test /health"))
            {
                ProbeHealth(agent.BackendBaseUrl);
            }
        }

        private void ProbeHealth(string baseUrl)
        {
            string url = $"{baseUrl.TrimEnd('/')}/health";
            var req = UnityWebRequest.Get(url);
            var op = req.SendWebRequest();
            op.completed += _ =>
            {
                _healthStatus = req.result == UnityWebRequest.Result.Success
                    ? $"{req.responseCode} {req.downloadHandler.text}"
                    : $"ERROR: {req.error}";
                req.Dispose();
                Repaint();
            };
        }
    }
}
