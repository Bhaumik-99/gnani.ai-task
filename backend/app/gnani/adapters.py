"""Gnani provider boundaries; exact API contracts must be verified first."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    model: str
    configured: bool


class GnaniNotConfigured(RuntimeError):
    pass


class GnaniAdapters:
    def __init__(self, settings):
        self.settings = settings

    def statuses(self):
        return [
            asdict(ProviderStatus("prisma", self.settings.gnani_prisma_model,
                                 bool(self.settings.gnani_api_key and self.settings.gnani_prisma_ws_url))),
            asdict(ProviderStatus("evon", self.settings.gnani_evon_model,
                                 bool(self.settings.gnani_api_key and self.settings.gnani_evon_url))),
            asdict(ProviderStatus("timbre", self.settings.gnani_timbre_model,
                                 bool(self.settings.gnani_api_key and self.settings.gnani_timbre_ws_url))),
            asdict(ProviderStatus("warp", self.settings.gnani_warp_model,
                                 bool(self.settings.gnani_api_key and self.settings.gnani_warp_url))),
        ]

    async def transcribe(self, *_args, **_kwargs):
        raise GnaniNotConfigured("Prisma live adapter pending verified Gnani API contract.")

    async def reason(self, *_args, **_kwargs):
        raise GnaniNotConfigured("Evon adapter pending verified Gnani API contract.")

    async def synthesize(self, *_args, **_kwargs):
        raise GnaniNotConfigured("Timbre live adapter pending verified Gnani API contract.")

    async def enhance_audio(self, *_args, **_kwargs):
        raise GnaniNotConfigured("No verified Warp audio-enhancement operation is configured.")
