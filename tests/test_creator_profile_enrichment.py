import json
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from ugc_tagger.creator_profile_enrichment import (
    DEFAULT_PROFILE_HISTORY_MODE,
    DEFAULT_PROFILE_POST_LIMIT,
    FULL_PROFILE_POST_CEILING,
    INSTAGRAM_APIFY_FALLBACK_POST_LIMIT,
    INSTAGRAM_PROFILE_ACTOR_ID,
    PROFILE_HISTORY_FULL,
    PROFILE_HISTORY_LATEST,
    PROFILE_HISTORY_OPTIONS,
    PROFILE_SCOPE_OPTIONS,
    TIKTOK_PROFILE_ACTOR_ID,
    _collect_tiktok_full_window,
    _extract_instagram_user_full_window,
    _extract_tiktok_user_full_window,
    creator_profile_url,
    fetch_direct_creator_profile_metrics,
    fetch_tiktok_profile_followers,
    instagram_profile_requires_fallback,
    normalize_creator_handle,
    profile_history_settings,
    profile_scope_count,
    scrape_creator_profile_metrics,
    tiktok_profile_requires_fallback,
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
    def test_tiktok_followers_only_reads_profile_header_without_post_scraping(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"uniqueId":"Alice","secUid":"sec-alice"},'
            '"stats":{"followerCount":12345,"videoCount":99}}'
            "</script>"
        )
        requested_urls = []

        followers = fetch_tiktok_profile_followers(
            "@Alice",
            profile_fetcher=lambda url: requested_urls.append(url) or profile_html,
            playlist_extractor=lambda _query, _limit: self.fail(
                "Profile-header followers must not invoke the playlist fallback."
            ),
        )

        self.assertEqual(followers, 12_345)
        self.assertEqual(requested_urls, ["https://www.tiktok.com/@Alice"])

    def test_tiktok_followers_only_distinguishes_zero_from_missing_hydration(self):
        zero_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"uniqueId":"new-account","secUid":"sec-new"},'
            '"stats":{"followerCount":0}}'
            "</script>"
        )
        self.assertEqual(
            fetch_tiktok_profile_followers(
                "new-account",
                profile_fetcher=lambda _url: zero_html,
            ),
            0,
        )

        with self.assertRaisesRegex(RuntimeError, "did not return"):
            fetch_tiktok_profile_followers(
                "blocked",
                profile_fetcher=lambda _url: "<html>blocked</html>",
                playlist_extractor=lambda _query, _limit: {"id": "sec-blocked"},
                profile_stats_fetcher=lambda _sec_uid, _creator: {
                    "itemList": [{
                        "author": {
                            "uniqueId": "someone-else",
                            "secUid": "sec-someone-else",
                        },
                        "authorStats": {"followerCount": 999_999},
                    }],
                },
            )

    def test_tiktok_followers_only_wraps_one_profile_fetch_failure(self):
        with self.assertRaisesRegex(RuntimeError, "could not be retrieved"):
            fetch_tiktok_profile_followers(
                "broken",
                profile_fetcher=lambda _url: (_ for _ in ()).throw(TimeoutError()),
                playlist_extractor=lambda _query, _limit: (
                    _ for _ in ()
                ).throw(TimeoutError()),
            )

    def test_tiktok_followers_only_uses_verified_public_stats_fallback(self):
        calls = []

        followers = fetch_tiktok_profile_followers(
            "Alice",
            representative_post_url="https://www.tiktok.com/@alice/video/123",
            profile_fetcher=lambda _url: "<html>challenge</html>",
            post_extractor=lambda post_url: calls.append(
                ("post", post_url)
            ) or {"uploader": "alice", "channel_id": "sec-alice"},
            playlist_extractor=lambda _query, _limit: self.fail(
                "A verified post identity must avoid the profile playlist fallback."
            ),
            profile_stats_fetcher=lambda sec_uid, creator: calls.append(
                ("stats", sec_uid, creator)
            ) or {
                "itemList": [{
                    "author": {"uniqueId": "alice", "secUid": "sec-alice"},
                    "authorStats": {"followerCount": 91_200},
                }],
            },
        )

        self.assertEqual(followers, 91_200)
        self.assertEqual(calls, [
            ("post", "https://www.tiktok.com/@alice/video/123"),
            ("stats", "sec-alice", "Alice"),
        ])

    def test_tiktok_profile_header_rejects_unrelated_follower_without_identity(self):
        unrelated_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"recommended":{"stats":{"followerCount":888888}}}'
            "</script>"
        )
        with self.assertRaisesRegex(RuntimeError, "did not return"):
            fetch_tiktok_profile_followers(
                "alice",
                profile_fetcher=lambda _url: unrelated_html,
                playlist_extractor=lambda _query, _limit: {"id": "sec-alice"},
                profile_stats_fetcher=lambda _sec_uid, _creator: {"itemList": []},
            )

    def test_tiktok_profile_header_rejects_unrelated_identity_and_followers(self):
        unrelated_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"recommended":{"user":{"uniqueId":"someone-else",'
            '"secUid":"sec-other"},"stats":{"followerCount":888888}}}'
            "</script>"
        )
        with self.assertRaisesRegex(RuntimeError, "did not return"):
            fetch_tiktok_profile_followers(
                "alice",
                profile_fetcher=lambda _url: unrelated_html,
                playlist_extractor=lambda _query, _limit: {"id": "sec-alice"},
                profile_stats_fetcher=lambda _sec_uid, _creator: {"itemList": []},
            )

    def test_tiktok_profile_fallback_requires_followers_and_available_status(self):
        base = pd.DataFrame([{
            "Platform": TIKTOK,
            "Current Followers": 800,
            "Profile Data Status": "Available",
        }])
        self.assertFalse(tiktok_profile_requires_fallback(base))

        no_recent = base.copy()
        no_recent["Profile Data Status"] = "No recent public posts"
        self.assertFalse(tiktok_profile_requires_fallback(no_recent))

        partial = base.copy()
        partial["Profile Data Status"] = "Partial (2,000-post safety limit reached)"
        self.assertFalse(tiktok_profile_requires_fallback(partial))

        missing_followers = base.copy()
        missing_followers["Current Followers"] = 0
        self.assertTrue(tiktok_profile_requires_fallback(missing_followers))

        unavailable = base.copy()
        unavailable["Profile Data Status"] = "Unavailable"
        self.assertTrue(tiktok_profile_requires_fallback(unavailable))

    def test_instagram_profile_fallback_requires_followers_and_complete_history(self):
        base = pd.DataFrame([{
            "Platform": INSTAGRAM_REELS,
            "Current Followers": 800,
            "Profile Data Status": "Available (public metrics; shares/saves unavailable)",
        }])
        self.assertFalse(instagram_profile_requires_fallback(base))

        no_recent = base.copy()
        no_recent["Profile Data Status"] = "No recent public posts"
        self.assertFalse(instagram_profile_requires_fallback(no_recent))

        missing_followers = base.copy()
        missing_followers["Current Followers"] = 0
        self.assertTrue(instagram_profile_requires_fallback(missing_followers))

        partial = base.copy()
        partial["Profile Data Status"] = "Partial (full history may be incomplete)"
        self.assertTrue(instagram_profile_requires_fallback(partial))

    def test_instagram_profile_extractor_is_metadata_only_and_stops_at_cutoff(self):
        posts = [
            types.SimpleNamespace(
                mediaid="future", shortcode="future", date_utc="2026-08-09T00:00:00Z",
                video_view_count=999, likes=99, comments=9,
            ),
            types.SimpleNamespace(
                mediaid="recent", shortcode="recent", date_utc="2026-08-02T00:00:00Z",
                video_view_count=300, likes=30, comments=3,
            ),
            types.SimpleNamespace(
                mediaid="old", shortcode="old", date_utc="2026-04-01T00:00:00Z",
                video_view_count=100, likes=10, comments=1,
            ),
        ]
        profile = types.SimpleNamespace(
            followers=800,
            get_posts=lambda: iter(posts),
        )

        class FakeLoader:
            kwargs = {}

            def __init__(self, **kwargs):
                FakeLoader.kwargs = kwargs
                self.context = object()

        fake_module = types.SimpleNamespace(
            Instaloader=FakeLoader,
            Profile=types.SimpleNamespace(
                from_username=lambda _context, handle: profile if handle == "ig-user" else None
            ),
        )
        with patch.dict(sys.modules, {"instaloader": fake_module}):
            result = _extract_instagram_user_full_window(
                "ig-user",
                "2026-05-08T00:00:00Z",
                "2026-08-08T00:00:00Z",
                2000,
            )

        self.assertEqual(result["followers"], 800)
        self.assertEqual([entry["id"] for entry in result["entries"]], ["recent"])
        self.assertTrue(result["complete"])
        self.assertFalse(FakeLoader.kwargs["download_pictures"])
        self.assertFalse(FakeLoader.kwargs["download_videos"])
        self.assertFalse(FakeLoader.kwargs["save_metadata"])

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
        self.assertEqual(PROFILE_SCOPE_OPTIONS, ("Top 5", "Top 10", "Top 20"))
        self.assertEqual(DEFAULT_PROFILE_POST_LIMIT, 20)
        self.assertEqual(DEFAULT_PROFILE_HISTORY_MODE, PROFILE_HISTORY_LATEST)
        self.assertEqual(
            PROFILE_HISTORY_OPTIONS,
            ("Latest 20 (fast)", "Full 3 months"),
        )
        self.assertEqual(FULL_PROFILE_POST_CEILING, 2000)
        self.assertEqual(INSTAGRAM_APIFY_FALLBACK_POST_LIMIT, 20)
        self.assertEqual(profile_history_settings(PROFILE_HISTORY_LATEST, 999), (PROFILE_HISTORY_LATEST, 20))
        self.assertEqual(profile_history_settings(PROFILE_HISTORY_FULL, 1), (PROFILE_HISTORY_FULL, 2000))
        self.assertEqual(profile_history_settings("unexpected", 7), (PROFILE_HISTORY_LATEST, 7))
        self.assertEqual(profile_scope_count("Top 5", 25), 5)
        self.assertEqual(profile_scope_count("Top 10", 25), 10)
        self.assertEqual(profile_scope_count("Top 20", 12), 12)
        self.assertEqual(profile_scope_count("All", 25), 5)

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
            post_limit=DEFAULT_PROFILE_POST_LIMIT,
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
        self.assertEqual(tiktok_input["profileSorting"], "latest")
        self.assertEqual(tiktok_input["resultsPerPage"], 20)
        self.assertEqual(tiktok_input["oldestPostDateUnified"], "3 months")
        self.assertFalse(tiktok_input["shouldDownloadVideos"])
        self.assertFalse(tiktok_input["shouldDownloadCovers"])
        instagram_posts_input = next(
            run_input for actor_id, run_input in client.calls
            if actor_id == INSTAGRAM_PROFILE_ACTOR_ID and run_input.get("resultsType") == "posts"
        )
        self.assertEqual(instagram_posts_input["onlyPostsNewerThan"], "3 months")
        self.assertEqual(instagram_posts_input["resultsLimit"], 20)

    def test_instagram_apify_fallback_stays_at_twenty_for_full_history_request(self):
        client = _FakeClient({
            f"{INSTAGRAM_PROFILE_ACTOR_ID}:posts": [],
            f"{INSTAGRAM_PROFILE_ACTOR_ID}:details": [],
        })

        scrape_creator_profile_metrics(
            [{"Platform": INSTAGRAM_REELS, "Creator": "alice"}],
            "test-token",
            client=client,
            months=3,
            post_limit=FULL_PROFILE_POST_CEILING,
            as_of="2026-08-04T00:00:00Z",
        )

        instagram_posts_input = next(
            run_input for actor_id, run_input in client.calls
            if actor_id == INSTAGRAM_PROFILE_ACTOR_ID
            and run_input.get("resultsType") == "posts"
        )
        self.assertEqual(
            instagram_posts_input["resultsLimit"],
            INSTAGRAM_APIFY_FALLBACK_POST_LIMIT,
        )
        self.assertEqual(instagram_posts_input["onlyPostsNewerThan"], "3 months")

    def test_tiktok_apify_fallback_honours_latest_twenty_request(self):
        client = _FakeClient({f"{TIKTOK_PROFILE_ACTOR_ID}:posts": []})

        scrape_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "alice"}],
            "test-token",
            client=client,
            months=3,
            post_limit=INSTAGRAM_APIFY_FALLBACK_POST_LIMIT,
            as_of="2026-08-04T00:00:00Z",
        )

        tiktok_input = next(
            run_input for actor_id, run_input in client.calls
            if actor_id == TIKTOK_PROFILE_ACTOR_ID
        )
        self.assertEqual(tiktok_input["resultsPerPage"], 20)
        self.assertEqual(tiktok_input["oldestPostDateUnified"], "3 months")

    def test_tiktok_apify_partial_response_keeps_missing_creator_unavailable(self):
        client = _FakeClient({
            f"{TIKTOK_PROFILE_ACTOR_ID}:posts": [{
                "createTimeISO": "2026-07-15T00:00:00Z",
                "authorMeta": {"name": "alice", "fans": 10_000},
                "playCount": 1_000,
                "diggCount": 100,
                "commentCount": 10,
            }],
        })

        metrics, errors = scrape_creator_profile_metrics(
            [
                {"Platform": TIKTOK, "Creator": "alice"},
                {"Platform": TIKTOK, "Creator": "bob"},
            ],
            "test-token",
            client=client,
            months=3,
            post_limit=20,
            as_of="2026-08-04T00:00:00Z",
        )

        alice = metrics[metrics["Creator Key"].eq("alice")].iloc[0]
        bob = metrics[metrics["Creator Key"].eq("bob")].iloc[0]
        self.assertEqual(alice["Profile Data Status"], "Available")
        self.assertEqual(bob["Profile Data Status"], "Unavailable")
        self.assertTrue(any("1 creator" in error for error in errors))

    def test_missing_token_is_rejected_without_a_client(self):
        with self.assertRaisesRegex(RuntimeError, "Missing Apify token"):
            scrape_creator_profile_metrics(
                [{"Platform": TIKTOK, "Creator": "alice"}],
                "",
            )

    def test_direct_tiktok_provider_uses_sec_uid_and_aggregates_metadata_only(self):
        profile_calls = []
        extractor_calls = []
        profile_payload = {
            "__DEFAULT_SCOPE__": {
                "webapp.user-detail": {
                    "userInfo": {
                        "user": {"secUid": "sec-alice"},
                        "stats": {"followerCount": 12_345},
                    }
                }
            }
        }
        profile_html = (
            '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
            f"{json.dumps(profile_payload)}"
            "</script>"
        )

        def profile_fetcher(url):
            profile_calls.append(url)
            return profile_html

        def extractor(query, limit):
            extractor_calls.append((query, limit))
            return {
                "entries": [
                    {
                        "id": "new",
                        "timestamp": 1_783_478_400,
                        "view_count": 1_000,
                        "like_count": 100,
                        "comment_count": 10,
                        "repost_count": 5,
                        "save_count": 7,
                        "url": "https://media.example/video.mp4",
                    },
                    {
                        "id": "new",
                        "timestamp": 1_783_478_400,
                        "view_count": 999_999,
                        "like_count": 999_999,
                    },
                    {
                        "id": "old",
                        "upload_date": "20260101",
                        "view_count": 99_000,
                        "like_count": 50_000,
                    },
                ]
            }

        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "@alice"}],
            months=3,
            post_limit=999,
            profile_fetcher=profile_fetcher,
            extractor=extractor,
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(profile_calls, ["https://www.tiktok.com/@alice"])
        self.assertEqual(extractor_calls, [("tiktokuser:sec-alice", 20)])
        self.assertEqual(len(metrics), 1)
        result = metrics.iloc[0]
        self.assertEqual(result["Profile Data Status"], "Available")
        self.assertEqual(int(result["Profile Posts"]), 1)
        self.assertEqual(int(result["Current Followers"]), 12_345)
        self.assertEqual(int(result["Profile Average Views"]), 1_000)
        self.assertEqual(int(result["Profile Average Engagement"]), 122)
        self.assertAlmostEqual(float(result["Profile Average Engagement Rate"]), 12.2)
        self.assertNotIn("url", metrics.columns)
        self.assertNotIn("media", metrics.columns)

    def test_direct_provider_isolates_failures_and_supports_instagram(self):
        profile_payload = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"UserModule":{"users":{"good":{"secUid":"sec-good"}},'
            '"stats":{"good":{"followerCount":500}}}}'
            "</script>"
        )

        def profile_fetcher(url):
            if url.endswith("/@broken"):
                raise TimeoutError("simulated timeout")
            return profile_payload

        def extractor(query, limit):
            self.assertEqual(query, "tiktokuser:sec-good")
            self.assertEqual(limit, 20)
            return {
                "entries": [{
                    "upload_date": "20260801",
                    "view_count": 200,
                    "like_count": 20,
                    "comment_count": 2,
                    "share_count": 1,
                }]
            }

        def instagram_extractor(handle, cutoff_utc, as_of_utc, cap):
            self.assertEqual(handle, "ig-user")
            self.assertEqual(cap, 20)
            return {
                "followers": 800,
                "entries": [{
                    "id": "ig-1",
                    "ownerUsername": handle,
                    "ownerFollowersCount": 800,
                    "timestamp": "2026-08-02T00:00:00Z",
                    "videoViewCount": 300,
                    "likesCount": 30,
                    "commentsCount": 3,
                }],
                "complete": True,
                "partial_reason": "",
            }

        metrics, errors = fetch_direct_creator_profile_metrics(
            [
                {"Platform": TIKTOK, "Creator": "good"},
                {"Platform": TIKTOK, "Creator": "broken"},
                {"Platform": INSTAGRAM_REELS, "Creator": "ig-user"},
            ],
            profile_fetcher=profile_fetcher,
            extractor=extractor,
            instagram_extractor=instagram_extractor,
            as_of="2026-08-08T00:00:00Z",
        )

        status_by_creator = metrics.set_index("Profile Creator")["Profile Data Status"].to_dict()
        self.assertEqual(status_by_creator["good"], "Available")
        self.assertEqual(status_by_creator["broken"], "Unavailable")
        self.assertEqual(
            status_by_creator["ig-user"],
            "Available (public metrics; shares/saves unavailable)",
        )
        self.assertEqual(int(metrics.loc[metrics["Profile Creator"].eq("good"), "Profile Posts"].iloc[0]), 1)
        self.assertEqual(int(metrics.loc[metrics["Profile Creator"].eq("ig-user"), "Profile Posts"].iloc[0]), 1)
        self.assertEqual(int(metrics.loc[metrics["Profile Creator"].eq("ig-user"), "Current Followers"].iloc[0]), 800)
        self.assertTrue(any("@broken" in error for error in errors))
        self.assertFalse(any("Instagram creator @ig-user" in error for error in errors))

    def test_direct_instagram_failure_is_isolated_and_marked_unavailable(self):
        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": INSTAGRAM_REELS, "Creator": "blocked-user"}],
            instagram_extractor=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("rate limited")
            ),
            as_of="2026-08-08T00:00:00Z",
        )
        self.assertEqual(metrics.iloc[0]["Profile Data Status"], "Unavailable")
        self.assertTrue(any("@blocked-user" in error for error in errors))

    def test_direct_provider_marks_empty_extraction_for_a_nonempty_profile_unavailable(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"secUid":"sec-blocked"},'
            '"stats":{"followerCount":1234,"videoCount":9}}'
            "</script>"
        )

        for empty_result in ({}, {"entries": []}, {"entries": [None]}):
            with self.subTest(empty_result=empty_result):
                metrics, errors = fetch_direct_creator_profile_metrics(
                    [{"Platform": TIKTOK, "Creator": "blocked"}],
                    profile_fetcher=lambda _url: profile_html,
                    extractor=lambda _query, _limit: empty_result,
                    as_of="2026-08-08T00:00:00Z",
                )

                self.assertTrue(errors)
                self.assertEqual(metrics.iloc[0]["Profile Data Status"], "Unavailable")

    def test_direct_provider_falls_back_to_public_profile_url_when_html_is_blocked(self):
        calls = []

        def full_extractor(query, cutoff_utc, as_of_utc, cap):
            calls.append((query, cutoff_utc, as_of_utc, cap))
            return {
                "entries": [{
                    "id": "one",
                    "upload_date": "20260801",
                    "view_count": 100,
                    "like_count": 10,
                }],
                "complete": True,
                "partial_reason": "",
            }

        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "blocked-html"}],
            history_mode=PROFILE_HISTORY_FULL,
            profile_fetcher=lambda _url: "<html>temporary anti-bot response</html>",
            full_extractor=full_extractor,
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(calls[0][0], "https://www.tiktok.com/@blocked-html")
        self.assertEqual(int(metrics.iloc[0]["Profile Posts"]), 1)
        self.assertEqual(
            metrics.iloc[0]["Profile Data Status"],
            "Available (followers unavailable)",
        )

    def test_latest_history_also_uses_public_profile_url_fallback(self):
        calls = []

        def extractor(query, limit):
            calls.append((query, limit))
            return {
                "entries": [{
                    "id": "one",
                    "upload_date": "20260801",
                    "view_count": 100,
                }]
            }

        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "blocked-latest"}],
            profile_fetcher=lambda _url: "",
            extractor=extractor,
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(calls, [("https://www.tiktok.com/@blocked-latest", 20)])
        self.assertEqual(int(metrics.iloc[0]["Profile Posts"]), 1)
        self.assertEqual(
            metrics.iloc[0]["Profile Data Status"],
            "Available (followers unavailable)",
        )

    def test_direct_provider_preserves_followers_when_no_posts_are_recent(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"secUid":"sec-old"},'
            '"stats":{"followerCount":12345,"videoCount":1}}'
            "</script>"
        )
        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "old-posts"}],
            profile_fetcher=lambda _url: profile_html,
            extractor=lambda _query, _limit: {
                "entries": [{
                    "id": "old",
                    "upload_date": "20250101",
                    "view_count": 100,
                    "like_count": 10,
                }]
            },
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(metrics.iloc[0]["Profile Data Status"], "No recent public posts")
        self.assertEqual(int(metrics.iloc[0]["Profile Posts"]), 0)
        self.assertEqual(int(metrics.iloc[0]["Current Followers"]), 12345)

    def test_direct_provider_skips_post_extraction_for_a_zero_post_profile(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"secUid":"sec-empty"},'
            '"stats":{"followerCount":25,"videoCount":0}}'
            "</script>"
        )

        def should_not_extract(_query, _limit):
            self.fail("A confirmed zero-post profile should not invoke yt-dlp.")

        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "empty"}],
            profile_fetcher=lambda _url: profile_html,
            extractor=should_not_extract,
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(metrics.iloc[0]["Profile Data Status"], "No recent public posts")
        self.assertEqual(int(metrics.iloc[0]["Current Followers"]), 25)

    def test_direct_provider_never_aggregates_more_than_twenty_posts_per_creator(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"secUid":"sec-capped"},"stats":{"followerCount":10}}'
            "</script>"
        )

        def extractor(query, limit):
            self.assertEqual(query, "tiktokuser:sec-capped")
            self.assertEqual(limit, 20)
            return {
                "entries": [
                    {
                        "upload_date": "20260801",
                        "view_count": index + 1,
                        "like_count": 1,
                    }
                    for index in range(25)
                ]
            }

        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "capped"}],
            post_limit=100,
            profile_fetcher=lambda _url: profile_html,
            extractor=extractor,
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(int(metrics.iloc[0]["Profile Posts"]), 20)

    def test_full_history_passes_cutoff_and_ceiling_and_aggregates_more_than_twenty(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"secUid":"sec-full"},"stats":{"followerCount":4321}}'
            "</script>"
        )
        calls = []

        def full_extractor(query, cutoff_utc, as_of_utc, cap):
            calls.append((query, cutoff_utc, as_of_utc, cap))
            return {
                "entries": [
                    {
                        "id": f"post-{index}",
                        "upload_date": "20260701",
                        "view_count": 100 + index,
                        "like_count": 10,
                        "comment_count": 1,
                        "url": "https://media.example/should-not-leak.mp4",
                    }
                    for index in range(30)
                ] + [{
                    "id": "post-0",
                    "upload_date": "20260701",
                    "view_count": 999999,
                    "like_count": 999999,
                }],
                "complete": True,
                "partial_reason": "",
            }

        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "full"}],
            history_mode=PROFILE_HISTORY_FULL,
            profile_fetcher=lambda _url: profile_html,
            full_extractor=full_extractor,
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)
        query, cutoff_utc, as_of_utc, cap = calls[0]
        self.assertEqual(query, "tiktokuser:sec-full")
        self.assertEqual(cutoff_utc, pd.Timestamp("2026-05-08T00:00:00Z"))
        self.assertEqual(as_of_utc, pd.Timestamp("2026-08-08T00:00:00Z"))
        self.assertEqual(cap, 2000)
        self.assertEqual(int(metrics.iloc[0]["Profile Posts"]), 30)
        self.assertEqual(int(metrics.iloc[0]["Current Followers"]), 4321)
        self.assertEqual(metrics.iloc[0]["Profile Data Status"], "Available")
        self.assertNotIn("url", metrics.columns)
        self.assertNotIn("media", metrics.columns)

    def test_full_window_stops_at_old_sentinel_and_includes_exact_cutoff(self):
        visited = []

        def entries():
            for entry in (
                {"id": "new", "upload_date": "20260801", "view_count": 10},
                {"id": "boundary", "upload_date": "20260508", "view_count": 20},
                {"id": "old", "upload_date": "20260507", "view_count": 30},
                {"id": "must-not-be-read", "upload_date": "20260802", "view_count": 40},
            ):
                visited.append(entry["id"])
                yield entry

        result = _collect_tiktok_full_window(
            entries(),
            cutoff_utc="2026-05-08T00:00:00Z",
            as_of_utc="2026-08-08T00:00:00Z",
            cap=500,
        )

        self.assertEqual([entry["id"] for entry in result["entries"]], ["new", "boundary"])
        self.assertEqual(visited, ["new", "boundary", "old"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["partial_reason"], "")

    def test_full_window_natural_exhaustion_is_complete_and_deduplicates(self):
        result = _collect_tiktok_full_window(
            [
                {"id": "one", "upload_date": "20260801", "view_count": 10},
                {"id": "one", "upload_date": "20260801", "view_count": 999},
                {"id": "two", "upload_date": "20260701", "view_count": 20},
            ],
            cutoff_utc="2026-05-08T00:00:00Z",
            as_of_utc="2026-08-08T00:00:00Z",
            cap=500,
        )

        self.assertTrue(result["complete"])
        self.assertEqual([entry["id"] for entry in result["entries"]], ["one", "two"])

    def test_full_window_uses_cap_plus_one_to_mark_partial(self):
        source = [
            {
                "id": f"post-{index}",
                "upload_date": "20260801",
                "view_count": index,
                "url": "https://media.example/video.mp4",
                "formats": [{"url": "https://media.example/video.mp4"}],
                "thumbnail": "https://media.example/cover.jpg",
            }
            for index in range(2001)
        ]
        result = _collect_tiktok_full_window(
            source,
            cutoff_utc="2026-05-08T00:00:00Z",
            as_of_utc="2026-08-08T00:00:00Z",
            cap=2000,
        )

        self.assertEqual(len(result["entries"]), 2000)
        self.assertFalse(result["complete"])
        self.assertIn("2000-post safety limit reached", result["partial_reason"])
        self.assertNotIn("url", result["entries"][0])
        self.assertNotIn("formats", result["entries"][0])
        self.assertNotIn("thumbnail", result["entries"][0])

    def test_full_window_missing_date_and_page_error_are_partial(self):
        missing_date = _collect_tiktok_full_window(
            [
                {"id": "missing", "view_count": 999},
                {"id": "valid", "upload_date": "20260801", "view_count": 10},
            ],
            cutoff_utc="2026-05-08T00:00:00Z",
            as_of_utc="2026-08-08T00:00:00Z",
        )
        self.assertFalse(missing_date["complete"])
        self.assertIn("no publish date", missing_date["partial_reason"])
        self.assertEqual(len(missing_date["entries"]), 1)

        def fails_after_one():
            yield {"id": "valid", "upload_date": "20260801", "view_count": 10}
            raise TimeoutError("simulated page failure")

        page_error = _collect_tiktok_full_window(
            fails_after_one(),
            cutoff_utc="2026-05-08T00:00:00Z",
            as_of_utc="2026-08-08T00:00:00Z",
        )
        self.assertFalse(page_error["complete"])
        self.assertIn("could not be read", page_error["partial_reason"])
        self.assertEqual(len(page_error["entries"]), 1)

        def fails_immediately():
            if False:
                yield None
            raise TimeoutError("simulated first-page failure")

        with self.assertRaisesRegex(RuntimeError, "could not be read"):
            _collect_tiktok_full_window(
                fails_immediately(),
                cutoff_utc="2026-05-08T00:00:00Z",
                as_of_utc="2026-08-08T00:00:00Z",
            )

    def test_full_window_skips_future_posts_and_marks_order_anomalies_partial(self):
        result = _collect_tiktok_full_window(
            [
                {"id": "future", "upload_date": "20260809", "view_count": 999},
                {"id": "july", "upload_date": "20260701", "view_count": 10},
                {"id": "august-out-of-order", "upload_date": "20260801", "view_count": 20},
            ],
            cutoff_utc="2026-05-08T00:00:00Z",
            as_of_utc="2026-08-08T00:00:00Z",
        )

        self.assertEqual(
            [entry["id"] for entry in result["entries"]],
            ["july", "august-out-of-order"],
        )
        self.assertFalse(result["complete"])
        self.assertIn("order could not be verified", result["partial_reason"])

    def test_full_partial_metrics_are_kept_without_adding_an_error(self):
        profile_html = (
            '<script id="SIGI_STATE" type="application/json">'
            '{"user":{"secUid":"sec-partial"},"stats":{"followerCount":55}}'
            "</script>"
        )
        metrics, errors = fetch_direct_creator_profile_metrics(
            [{"Platform": TIKTOK, "Creator": "partial"}],
            history_mode=PROFILE_HISTORY_FULL,
            profile_fetcher=lambda _url: profile_html,
            full_extractor=lambda _query, _cutoff, _as_of, _cap: {
                "entries": [{
                    "id": "one",
                    "upload_date": "20260801",
                    "view_count": 100,
                    "like_count": 10,
                }],
                "complete": False,
                "partial_reason": "some posts had no publish date",
            },
            as_of="2026-08-08T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(int(metrics.iloc[0]["Profile Posts"]), 1)
        self.assertEqual(int(metrics.iloc[0]["Current Followers"]), 55)
        self.assertEqual(
            metrics.iloc[0]["Profile Data Status"],
            "Partial (some posts had no publish date)",
        )

    def test_real_full_extractor_is_lazy_metadata_only_without_date_or_count_options(self):
        captured = {}

        class FakeDownloader:
            def __init__(self, options):
                captured["options"] = options

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, query, **kwargs):
                captured["query"] = query
                captured["kwargs"] = kwargs
                return {
                    "entries": iter([{
                        "id": "one",
                        "upload_date": "20260801",
                        "view_count": 10,
                        "url": "https://media.example/video.mp4",
                    }])
                }

        fake_module = types.SimpleNamespace(YoutubeDL=FakeDownloader)
        with patch.dict(sys.modules, {"yt_dlp": fake_module}):
            result = _extract_tiktok_user_full_window(
                "tiktokuser:sec-test",
                pd.Timestamp("2026-05-08T00:00:00Z"),
                pd.Timestamp("2026-08-08T00:00:00Z"),
                500,
            )

        options = captured["options"]
        self.assertEqual(captured["query"], "tiktokuser:sec-test")
        self.assertEqual(captured["kwargs"], {"download": False, "process": False})
        self.assertTrue(options["skip_download"])
        self.assertFalse(options["cachedir"])
        self.assertFalse(options["allow_playlist_files"])
        self.assertFalse(options["ignoreerrors"])
        self.assertTrue(options["lazy_playlist"])
        self.assertNotIn("playlistend", options)
        self.assertNotIn("daterange", options)
        self.assertNotIn("url", result["entries"][0])


if __name__ == "__main__":
    unittest.main()
