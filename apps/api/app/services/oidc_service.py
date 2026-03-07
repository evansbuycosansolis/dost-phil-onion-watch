from __future__ import annotations

import time
from typing import Any

import httpx
from jose import JWTError, jwt

from app.core.config import settings


class OIDCValidationError(ValueError):
    pass


_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _csv_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [segment.strip() for segment in raw.split(",") if segment.strip()]


def _cache_get(cache: dict[str, tuple[float, dict[str, Any]]], key: str) -> dict[str, Any] | None:
    hit = cache.get(key)
    if not hit:
        return None
    ts, payload = hit
    if (time.time() - ts) > max(1, settings.oidc_cache_ttl_seconds):
        return None
    return payload


def _cache_set(cache: dict[str, tuple[float, dict[str, Any]]], key: str, payload: dict[str, Any]) -> None:
    cache[key] = (time.time(), payload)


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise OIDCValidationError(f"Failed to fetch OIDC metadata from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OIDCValidationError(f"OIDC endpoint did not return an object: {url}")
    return payload


def oidc_discovery_document() -> dict[str, Any]:
    explicit = (settings.oidc_discovery_url or "").strip()
    issuer = (settings.oidc_issuer_url or "").strip().rstrip("/")
    if explicit:
        url = explicit
    elif issuer:
        url = f"{issuer}/.well-known/openid-configuration"
    else:
        raise OIDCValidationError("OIDC issuer/discovery URL is not configured")

    cached = _cache_get(_discovery_cache, url)
    if cached is not None:
        return cached

    payload = _fetch_json(url)
    _cache_set(_discovery_cache, url, payload)
    return payload


def oidc_jwks_document() -> dict[str, Any]:
    explicit = (settings.oidc_jwks_url or "").strip()
    if explicit:
        url = explicit
    else:
        discovery = oidc_discovery_document()
        jwks_uri = discovery.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri.strip():
            raise OIDCValidationError("OIDC discovery response is missing jwks_uri")
        url = jwks_uri.strip()

    cached = _cache_get(_jwks_cache, url)
    if cached is not None:
        return cached

    payload = _fetch_json(url)
    _cache_set(_jwks_cache, url, payload)
    return payload


def _claim_value(claims: dict[str, Any], path: str) -> Any:
    cursor: Any = claims
    for segment in path.split("."):
        if isinstance(cursor, dict):
            cursor = cursor.get(segment)
        else:
            return None
    return cursor


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return False


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(row).strip() for row in value if str(row).strip()]
    if isinstance(value, tuple):
        return [str(row).strip() for row in value if str(row).strip()]
    if isinstance(value, str):
        normalized = value.replace(";", ",").replace("|", ",")
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) == 1 and " " in parts[0]:
            return [part.strip() for part in parts[0].split(" ") if part.strip()]
        return parts
    return [str(value).strip()]


def oidc_signing_algorithms() -> list[str]:
    configured = _csv_values(settings.oidc_signing_algorithms)
    return configured or ["RS256", "HS256"]


def verify_oidc_id_token(id_token: str) -> dict[str, Any]:
    if not settings.oidc_enabled:
        raise OIDCValidationError("OIDC authentication is disabled")

    if not id_token or not id_token.strip():
        raise OIDCValidationError("Missing id_token")

    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")

    jwks = oidc_jwks_document()
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not keys:
        raise OIDCValidationError("OIDC JWKS payload is missing keys")

    selected_key: dict[str, Any] | None = None
    if kid:
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                selected_key = key
                break
    if selected_key is None:
        first = keys[0]
        if not isinstance(first, dict):
            raise OIDCValidationError("OIDC JWKS key shape is invalid")
        selected_key = first

    discovery = oidc_discovery_document()
    expected_issuer = (settings.oidc_issuer_url or "").strip() or str(discovery.get("issuer") or "").strip() or None
    expected_audience = (settings.oidc_audience or "").strip() or None
    options = {
        "verify_signature": True,
        "verify_aud": bool(expected_audience),
        "verify_iss": bool(expected_issuer),
    }

    try:
        claims = jwt.decode(
            id_token,
            selected_key,
            algorithms=oidc_signing_algorithms(),
            audience=expected_audience,
            issuer=expected_issuer,
            options=options,
        )
    except JWTError as exc:
        raise OIDCValidationError(f"OIDC token validation failed: {exc}") from exc

    if not isinstance(claims, dict):
        raise OIDCValidationError("OIDC token claims payload is invalid")
    return claims


def external_roles_from_claims(claims: dict[str, Any]) -> list[str]:
    role_claim = (settings.oidc_role_claim or "roles").strip()
    value = _claim_value(claims, role_claim)
    return _to_str_list(value)


def role_mapping_table() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pair in _csv_values(settings.oidc_role_mapping):
        if ":" not in pair:
            continue
        external, internal = pair.split(":", 1)
        ext = external.strip()
        inter = internal.strip()
        if ext and inter:
            mapping[ext] = inter
    return mapping


def mapped_local_roles(external_roles: list[str]) -> list[str]:
    mapping = role_mapping_table()
    mapped: set[str] = set()
    for role in external_roles:
        if role in mapping:
            mapped.add(mapping[role])
        elif role:
            mapped.add(role)
    return sorted(mapped)


def privileged_role_names() -> list[str]:
    return _csv_values(settings.oidc_privileged_roles)


def includes_privileged_role(role_names: list[str]) -> bool:
    privileged = set(privileged_role_names())
    return any(role in privileged for role in role_names)


def mfa_verified_from_claims(claims: dict[str, Any]) -> bool:
    boolean_claim = (settings.oidc_mfa_boolean_claim or "mfa").strip()
    if boolean_claim:
        bool_value = _claim_value(claims, boolean_claim)
        if _to_bool(bool_value):
            return True

    amr_claim = (settings.oidc_mfa_claim or "amr").strip()
    methods = set(_csv_values(settings.oidc_mfa_methods))
    amr_values = {value.lower() for value in _to_str_list(_claim_value(claims, amr_claim))}
    if methods and amr_values.intersection({value.lower() for value in methods}):
        return True

    acr_claim = (settings.oidc_mfa_acr_claim or "acr").strip()
    acr_values = {value.lower() for value in _to_str_list(_claim_value(claims, acr_claim))}
    acr_accepted = {value.lower() for value in _csv_values(settings.oidc_mfa_acr_values)}
    if acr_values and acr_accepted and acr_values.intersection(acr_accepted):
        return True
    if acr_values and any("mfa" in value for value in acr_values):
        return True
    return False


def identity_from_claims(claims: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    subject_claim = (settings.oidc_subject_claim or "sub").strip()
    email_claim = (settings.oidc_email_claim or "email").strip()
    name_claim = (settings.oidc_name_claim or "name").strip()

    subject = _claim_value(claims, subject_claim)
    email = _claim_value(claims, email_claim)
    full_name = _claim_value(claims, name_claim)

    normalized_subject = str(subject).strip() if subject is not None and str(subject).strip() else None
    normalized_email = str(email).strip().lower() if email is not None and str(email).strip() else None
    normalized_name = str(full_name).strip() if full_name is not None and str(full_name).strip() else None
    return normalized_subject, normalized_email, normalized_name
