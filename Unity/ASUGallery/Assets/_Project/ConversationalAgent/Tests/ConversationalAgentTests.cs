using NUnit.Framework;
using UnityEngine;

namespace ASUMuseum.ConversationalAgent.Tests
{
    public class ArtworkContextTests
    {
        [TearDown]
        public void Cleanup() => ArtworkContext.Current = null;

        [Test]
        public void Current_DefaultsToNull()
        {
            Assert.IsNull(ArtworkContext.Current);
        }

        [Test]
        public void IsValid_FalseWhenIdMissing()
        {
            var ctx = new ArtworkContext { Title = "x" };
            Assert.IsFalse(ctx.IsValid);
        }

        [Test]
        public void Current_RoundTripsViaQueryRequest()
        {
            ArtworkContext.Current = new ArtworkContext
            {
                ArtworkId = "tamalada",
                Title = "Tamalada",
                Year = "1987",
                Medium = "gouache on paper",
            };

            var req = new ConversationalAgent.QueryRequest
            {
                session_id = "s1",
                artwork_id = ArtworkContext.Current.ArtworkId,
                query_text = "tell me about this",
                language = "en",
                visited_artworks = new[] { "sandia" },
            };

            string json = JsonUtility.ToJson(req);
            StringAssert.Contains("\"artwork_id\":\"tamalada\"", json);
            StringAssert.Contains("\"session_id\":\"s1\"", json);
            StringAssert.Contains("\"sandia\"", json);
        }
    }
}
