using System;
using UnityEngine;

namespace ASUMuseum.ConversationalAgent
{
    /// <summary>
    /// Microphone wrapper. StartRecording() begins a buffered capture; StopRecording()
    /// returns the captured audio as 16-bit PCM WAV bytes (in-memory).
    ///
    /// Caveat from the project brief: the Microphone API has ~200 ms of leading
    /// silence on Quest. We trim that on stop.
    /// </summary>
    public class VoiceCapture : MonoBehaviour
    {
        [SerializeField] private int sampleRate = 16000;
        [SerializeField] private int maxRecordSeconds = 30;
        [SerializeField] private float leadingTrimSeconds = 0.2f;

        private AudioClip _clip;
        private string _device;
        private bool _recording;

        public bool IsRecording => _recording;

        public void StartRecording()
        {
            if (_recording) return;
            if (Microphone.devices.Length == 0)
            {
                Debug.LogWarning("[VoiceCapture] No microphone devices available.");
                return;
            }
            _device = Microphone.devices[0];
            _clip = Microphone.Start(_device, false, maxRecordSeconds, sampleRate);
            _recording = true;
        }

        /// <summary>
        /// Stops capture and returns the recorded audio as a 16-bit PCM WAV byte buffer.
        /// </summary>
        public byte[] StopRecording()
        {
            if (!_recording || _clip == null) return Array.Empty<byte>();
            int writePos = Microphone.GetPosition(_device);
            Microphone.End(_device);
            _recording = false;

            if (writePos <= 0) return Array.Empty<byte>();

            int channels = _clip.channels;
            var samples = new float[writePos * channels];
            _clip.GetData(samples, 0);

            int trimSamples = Mathf.Min(
                (int)(leadingTrimSeconds * sampleRate) * channels,
                samples.Length);
            int finalLen = samples.Length - trimSamples;
            var trimmed = new float[finalLen];
            Array.Copy(samples, trimSamples, trimmed, 0, finalLen);

            return EncodeWav(trimmed, sampleRate, channels);
        }

        private static byte[] EncodeWav(float[] samples, int sampleRate, int channels)
        {
            short[] pcm = new short[samples.Length];
            for (int i = 0; i < samples.Length; i++)
            {
                float s = Mathf.Clamp(samples[i], -1f, 1f);
                pcm[i] = (short)(s * short.MaxValue);
            }

            int byteRate = sampleRate * channels * 2;
            int dataSize = pcm.Length * 2;
            byte[] wav = new byte[44 + dataSize];

            // RIFF header
            System.Text.Encoding.ASCII.GetBytes("RIFF").CopyTo(wav, 0);
            BitConverter.GetBytes(36 + dataSize).CopyTo(wav, 4);
            System.Text.Encoding.ASCII.GetBytes("WAVE").CopyTo(wav, 8);

            // fmt chunk
            System.Text.Encoding.ASCII.GetBytes("fmt ").CopyTo(wav, 12);
            BitConverter.GetBytes(16).CopyTo(wav, 16);
            BitConverter.GetBytes((short)1).CopyTo(wav, 20); // PCM
            BitConverter.GetBytes((short)channels).CopyTo(wav, 22);
            BitConverter.GetBytes(sampleRate).CopyTo(wav, 24);
            BitConverter.GetBytes(byteRate).CopyTo(wav, 28);
            BitConverter.GetBytes((short)(channels * 2)).CopyTo(wav, 32);
            BitConverter.GetBytes((short)16).CopyTo(wav, 34);

            // data chunk
            System.Text.Encoding.ASCII.GetBytes("data").CopyTo(wav, 36);
            BitConverter.GetBytes(dataSize).CopyTo(wav, 40);
            Buffer.BlockCopy(pcm, 0, wav, 44, dataSize);

            return wav;
        }
    }
}
