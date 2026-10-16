"""ElevenLabs voice adapter (plain httpx): signed conversation URLs and spoken briefings.

Read-only by design. The agent can only call our verified webhook (see
`security/webhooks.ElevenLabsWebhookVerifier`) with read intents or a replay *request*;
a replay still needs an authenticated operator on the dashboard/API. Briefing text is
templated from persisted findings (`application.voice.build_briefing`), never model text.
"""

import re
from typing import Final
from urllib.parse import urlsplit

import httpx

from gauntlet.contracts import VoiceBriefing
from gauntlet.ports.errors import EnvironmentUnavailableError
from gauntlet.settings import IntegrationSettings, require

DEFAULT_API_URL: Final = "https://api.elevenlabs.io"
_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_MAX_AUDIO_BYTES: Final = 10_000_000


class ElevenLabsVoice:
    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        voice_id: str | None = None,
        api_url: str = DEFAULT_API_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key is required")
        if not _ID.fullmatch(agent_id) or (voice_id is not None and not _ID.fullmatch(voice_id)):
            raise ValueError("ElevenLabs agent/voice ID is invalid")
        self._api_key = api_key
        self._agent_id = agent_id
        self._voice_id = voice_id
        self._api_url = api_url.rstrip("/")
        self._transport = transport

    @classmethod
    def from_settings(
        cls, settings: IntegrationSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> "ElevenLabsVoice":
        if not settings.core.run_live_integrations:
            raise EnvironmentUnavailableError("missing RUN_LIVE_INTEGRATIONS=1 for ElevenLabs")
        config = require("elevenlabs", settings.elevenlabs)
        return cls(
            api_key=config.api_key.reveal(),
            agent_id=config.agent_id,
            voice_id=config.voice_id,
            transport=transport,
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._api_url,
            transport=self._transport,
            timeout=20.0,
            follow_redirects=False,
            trust_env=False,
            headers={"xi-api-key": self._api_key},
        )

    async def check_auth(self) -> None:
        """Cheap authenticated read (no usage cost). Raises if the key is rejected."""
        async with self._client() as client:
            try:
                response = await client.get("/v1/user")
            except httpx.HTTPError as exc:
                raise EnvironmentUnavailableError(
                    f"ElevenLabs request failed ({type(exc).__name__})"
                ) from None
        if response.status_code != 200:
            raise EnvironmentUnavailableError(f"ElevenLabs auth check HTTP {response.status_code}")

    async def signed_conversation_url(self) -> str:
        """Short-lived wss URL the dashboard uses to talk to the agent without our key."""
        async with self._client() as client:
            try:
                response = await client.get(
                    "/v1/convai/conversation/get-signed-url", params={"agent_id": self._agent_id}
                )
            except httpx.HTTPError as exc:
                raise EnvironmentUnavailableError(
                    f"ElevenLabs request failed ({type(exc).__name__})"
                ) from None
        if response.status_code != 200:
            raise EnvironmentUnavailableError(f"ElevenLabs signed URL HTTP {response.status_code}")
        body = response.json()
        url = body.get("signed_url") if isinstance(body, dict) else None
        if not isinstance(url, str) or urlsplit(url).scheme != "wss":
            raise EnvironmentUnavailableError("ElevenLabs returned no signed URL")
        return url

    async def speak_briefing(self, briefing: VoiceBriefing) -> bytes:
        """MP3 of the templated `spoken_summary`. Needs ELEVENLABS_VOICE_ID."""
        if self._voice_id is None:
            raise EnvironmentUnavailableError("missing ELEVENLABS_VOICE_ID")
        async with self._client() as client:
            try:
                response = await client.post(
                    f"/v1/text-to-speech/{self._voice_id}",
                    params={"output_format": "mp3_44100_128"},
                    json={"text": briefing.spoken_summary, "model_id": "eleven_multilingual_v2"},
                )
            except httpx.HTTPError as exc:
                raise EnvironmentUnavailableError(
                    f"ElevenLabs request failed ({type(exc).__name__})"
                ) from None
        if response.status_code != 200 or not response.content:
            raise EnvironmentUnavailableError(f"ElevenLabs TTS HTTP {response.status_code}")
        if len(response.content) > _MAX_AUDIO_BYTES:
            raise EnvironmentUnavailableError("ElevenLabs audio exceeded the size limit")
        return response.content
