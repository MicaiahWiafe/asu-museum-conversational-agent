using System;

namespace ASUMuseum.ConversationalAgent
{
    /// <summary>
    /// Lightweight, serializable description of the artwork the visitor is currently
    /// engaged with. Set by gaze/proximity triggers; consumed by ConversationalAgent
    /// when building the /query payload. Use the static <see cref="Current"/> property
    /// to communicate context across components without coupling them.
    /// </summary>
    [Serializable]
    public class ArtworkContext
    {
        public string ArtworkId;
        public string Title;
        public string Year;
        public string Medium;

        public static ArtworkContext Current { get; set; }

        public bool IsValid => !string.IsNullOrEmpty(ArtworkId);
    }
}
