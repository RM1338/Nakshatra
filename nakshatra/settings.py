"""Configuration: env (secrets, paths) -> config.yaml (algorithm params) -> per-run budget (LLD §2)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    serpapi_api_key: str = ""
    nakshatra_db: Path = Path("data/nakshatra.db")
    nakshatra_offline: bool = False
    nakshatra_host: str = "127.0.0.1"
    nakshatra_port: int = 8000


class BudgetCfg(BaseModel):
    default: int = 60
    min: int = 20
    max: int = 200
    split: tuple[float, float, float] = (0.20, 0.65, 0.15)  # sample, expand, refine


class PriorCfg(BaseModel):
    weights: tuple[float, float, float, float, float, float] = (-1.0, 2.0, 0.8, 0.5, 0.6, 0.7)


class ExpandCfg(BaseModel):
    hot_boost: float = 0.5
    refine_every: int = 5
    plateau_eps: float = 0.02
    plateau_window: int = 8
    backfill_cap: int = 5


class RingCfg(BaseModel):
    min_users: int = 4
    min_places: int = 3
    min_coverage: float = 0.5
    max_rings: int = 5


class StatsCfg(BaseModel):
    alpha: float = 0.01
    mass_scale: float = 1.0
    n_perm: int = 200
    n_perm_max: int = 500
    perm_seed: int = 11


class TimeCfg(BaseModel):
    delta_days: float = 14.0
    lockstep_share: float = 0.6
    max_median_width_days: float = 30.0


class RatingCfg(BaseModel):
    kappa: float = 5.0
    tau: float = 1.0
    bootstrap_n: int = 1000
    bootstrap_seed: int = 7


class SerpCfg(BaseModel):
    json_restrictor: bool = False  # DECISIONS C2: off until the syntax is verified (T02)


class Config(BaseModel):
    model_config = {"frozen": True}
    budget: BudgetCfg = Field(default_factory=BudgetCfg)
    prior: PriorCfg = Field(default_factory=PriorCfg)
    expand: ExpandCfg = Field(default_factory=ExpandCfg)
    ring: RingCfg = Field(default_factory=RingCfg)
    stats: StatsCfg = Field(default_factory=StatsCfg)
    time: TimeCfg = Field(default_factory=TimeCfg)
    rating: RatingCfg = Field(default_factory=RatingCfg)
    serp: SerpCfg = Field(default_factory=SerpCfg)
    narrator_enabled: bool = False

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


def load_config(path: Path = Path("config.yaml")) -> Config:
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    return Config.model_validate(data or {})
