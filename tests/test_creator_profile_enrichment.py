import unittest

import pandas as pd

from ugc_tagger.creator_profile_enrichment import (
    INSTAGRAM_PROFILE_ACTOR_ID,
    TIKTOK_PROFILE_ACTOR_ID,
    creator_profile_url,
    normalize_creator_handle,
    profile_scope_count,
    scrape_creator_profile_metrics,
)
from ugc_tagger.instagram_reels_adapter import INSTAGRAM_REELS, TIKTOK


class _FakeDataset:
    def __init__(self, items):
        self.items = items

    def iterate_items(self):
        return iter(self.items)


class _FakeActor:
    def __init__(self, client, actor_id):
        self.client = client
        self.actor_id = actor_id

    def call(self, run_input):
        self.client.calls.append((self.actor_id, run_input))
        result_type = run_input.get("resultsType", "posts")
        dataset_id = f"{self.actor_id}:{result_type}"
        return {"defaultDatasetId": dataset_id}


class _FakeClient:
    def __init__(self, datasets):
        self.datasets = datasets
        self.calls = []

    def actor(self, actor_id):
        return _FakeActor(self, actor_id)

    def dataset(self, dataset_id):
        return _FakeDataset(self.datasets.get(dataset_id, []))


class CreatorProfileEnrichmentTests(unittest.TestCase):
    def test_creator_profile_links_and_scope(self):
        self.assertEqual(normalize_creator_handle("@alice"), "alice")
        self.assertEqual(
            normalize_creator_handle("https://www.instagram.com/alice/"),
            "alice",
        )
        self.assertEqual(
            creator_profile_url(TIKTOK, "@alice"),
            "https://www.tiktok.com/@alice",
        )
        self.assertEqual(
            creator_profile_url(INSTAGRAM_REELS, "alice"),
            "https://www.instagram.com/alice/",
        )
        self.assertEqual(profile_scope_count("Top 10", 25), 10)
        self.assertEqual(profile_scope_count("Top 20", 12), 12)
        self.assertEqual(profile_scope_count("All", 25), 25)

    def test_scrape_uses_metadata_only_and_aggregates_both_platforms(self):
        client = _FakeClient({
            f"{TIKTOK_PROFILE_ACTOR_ID}:posts": [
                {
                    "createTimeISO": "2026-07-15T00:00:00Z",
                    "authorMeta": {"name": "alice", "fans": 10_000},
                    "playCount": 1_000,
                    "diggCount": 100,
                    "commentCount": 10,
                    "shareCount": 5,
                    "collectCount": 5,
                },
                {
                    "createTimeISO": "2026-01-01T00:00:00Z",
                    "authorMeta": {"name": "alice", "fans": 9_000},
                    "playCount": 99_000,
                    "diggCount": 50_000,
                },
            ],
            f"{INSTAGRAM_PROFILE_ACTOR_ID}:posts": [
                {
                    "timestamp": "2026-07-20T00:00:00Z",
                    "ownerUsername": "bob",
                    "videoPlayCount": 2_000,
                    "likesCount": 200,
                    "commentsCount": 20,
                },
            ],
            f"{INSTAGRAM_PROFILE_ACTOR_ID}:details": [
                {"username": "bob", "followersCount": 30_000},
            ],
        })
        creators = pd.DataFrame([
            {"Platform": TIKTOK, "Creator": "@alice"},
            {"Platform": INSTAGRAM_REELS, "Creator": "bob"},
        ])

        metrics, errors = scrape_creator_profile_metrics(
            creators,
            "test-token",
            client=client,
            months=3,
            post_limit=200,
            as_of="2026-08-04T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(metrics), 2)
        tiktok = metrics[metrics["Platform"] == TIKTOK].iloc[0]
        instagram = metrics[metrics["Platform"] == INSTAGRAM_REELS].iloc[0]
        self.assertEqual(int(tiktok["Profile Posts"]), 1)
        self.assertEqual(int(tiktok["Current Followers"]), 10_000)
        self.assertEqual(int(tiktok["Profile Average Views"]), 1_000)
        self.assertEqual(int(tiktok["Profile Average Engagement"]), 120)
        self.assertAlmostEqual(float(tiktok["Profile Average Engagement Rate"]), 12.0)
        self.assertEqual(int(instagram["Profile Posts"]), 1)
        self.assertEqual(int(instagram["Current Followers"]), 30_000)
        self.assertEqual(int(instagram["Profile Average Engagement"]), 220)
        self.assertAlmostEqual(float(instagram["Profile Average Engagement Rate"]), 11.0)

        tiktok_input = next(
            run_input for actor_id, run_input in client.calls
            if actor_id == TIKTOK_PROFILE_ACTOR_ID
        )
        self.assertEqual(tiktok_input["profiles"], ["alice"])
        self.assertEqual(tiktok_input["oldestPostDateUnified"], "3 months")
        self.assertFalse(tiktok_input["shouldDownloadVideos"])
        self.assertFalse(tiktok_input["shouldDownloadCovers"])
        instagram_posts_input = next(
            run_input for actor_id, run_input in client.calls
            if actor_id == INSTAGRAM_PROFILE_ACTOR_ID and run_input.get("resultsType") == "posts"
        )
        self.assertEqual(instagram_posts_input["onlyPostsNewerThan"], "3 months")
        self.assertEqual(instagram_posts_input["resultsLimit"], 200)

    def test_missing_token_is_rejected_without_a_client(self):
        with self.assertRaisesRegex(RuntimeError, "Missing Apify token"):
            scrape_creator_profile_metrics(
                [{"Platform": TIKTOK, "Creator": "alice"}],
                "",
            )


if __name__ == "__main__":
    unittest.main()
