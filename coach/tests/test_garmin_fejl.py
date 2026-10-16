"""Opg. 3: en netværksfejl hos Garmin er ikke et afvist login."""

import socket

import garminconnect
import pytest
import requests
from garminconnect import (GarminConnectAuthenticationError, GarminConnectConnectionError,
                           GarminConnectTooManyRequestsError)

from garmin_coach import ingest_garmin as ig
from garmin_coach.config import CONFIG

DNS = ("HTTPSConnectionPool(host='connectapi.garmin.com', port=443): Max retries exceeded with url: "
       "/userprofile-service/socialProfile (Caused by NameResolutionError(\"HTTPSConnection(host='connectapi.garmin.com', "
       "port=443): Failed to resolve 'connectapi.garmin.com' ([Errno 8] nodename nor servname provided, or not known)\"))")


def _rejst(exc: BaseException, fra: BaseException | None = None) -> BaseException:
    """En undtagelse med kæde, som når garminconnect rejser `exc from fra`."""
    try:
        try:
            if fra is not None:
                raise fra
        except BaseException as indre:
            raise exc from indre
        raise exc
    except BaseException as e:  # noqa: BLE001
        return e


def social_profil_dns():
    # Sådan kan det se ud i loggen: en DNS-fejl pakket ind som en login-fejl
    return _rejst(GarminConnectAuthenticationError("Failed to retrieve social profile"),
                  requests.exceptions.ConnectionError(DNS))


@pytest.mark.parametrize("exc", [
    social_profil_dns(),
    _rejst(GarminConnectConnectionError(f"Login failed: {DNS}")),
    _rejst(GarminConnectAuthenticationError("x"), socket.gaierror(8, "nodename nor servname provided, or not known")),
    _rejst(GarminConnectConnectionError("API Error"), TimeoutError("The read operation timed out")),
    _rejst(GarminConnectConnectionError("All login strategies exhausted: Could not resolve host: sso.garmin.com")),
])
def test_netvaerksfejl_genkendes(exc):
    assert ig.netvaerksaarsag(exc)


@pytest.mark.parametrize("exc", [
    _rejst(GarminConnectAuthenticationError("Authentication failed (401 Unauthorized)")),
    _rejst(GarminConnectAuthenticationError("Failed to retrieve social profile"),
           requests.exceptions.HTTPError("401 Client Error: Unauthorized for url: https://connectapi.garmin.com/x")),
    _rejst(GarminConnectAuthenticationError("MFA verification failed: wrong code")),
])
def test_auth_fejl_er_ikke_netvaerk(exc):
    assert ig.netvaerksaarsag(exc) is None


def test_aarsagen_viser_ingen_forespoergsel():
    exc = _rejst(GarminConnectConnectionError("Login failed"),
                 requests.exceptions.ConnectionError("Max retries exceeded with url: /sso/login?ticket=ST-HEMMELIG-1"))
    assert "HEMMELIG" not in ig.netvaerksaarsag(exc)


@pytest.fixture
def garmin(monkeypatch, tmp_path):
    """Et falsk garminconnect.Garmin, hvis login rejser det, testen sætter. Intet netværk."""
    monkeypatch.setattr(CONFIG, "token_dir", tmp_path)  # findes, så login bruger "gemte tokens"
    monkeypatch.setattr(ig, "_garmin_kan_slaas_op", lambda: True)
    rejs = {}

    class FalskGarmin:
        display_name = "test"

        def __init__(self, *a, **kw):
            pass

        def login(self, tokendir):
            if "exc" in rejs:
                raise rejs["exc"]

    monkeypatch.setattr(garminconnect, "Garmin", FalskGarmin)
    return rejs


def test_login_dns_fejl_giver_netvaerksbesked(garmin):
    garmin["exc"] = social_profil_dns()
    with pytest.raises(ig.GarminNetvaerksfejl, match=r"^Kunne ikke nå Garmin \(netværk\)") as info:
        ig.login()
    assert "afviste dit login" not in str(info.value) and "password i .env" not in str(info.value)


def test_login_forkert_password_giver_loginbesked(garmin):
    garmin["exc"] = _rejst(GarminConnectAuthenticationError("Authentication failed (401 Unauthorized)"))
    with pytest.raises(ig.GarminLoginAfvist, match="^Garmin afviste dit login"):
        ig.login()


def test_login_uden_spor_men_dns_svarer_ikke_er_netvaerk(garmin, monkeypatch):
    # Tokens kunne ikke fornys offline, så garminconnect beder om password uden at sige hvorfor
    garmin["exc"] = _rejst(GarminConnectAuthenticationError("Username and password are required"))
    monkeypatch.setattr(ig, "_garmin_kan_slaas_op", lambda: False)
    with pytest.raises(ig.GarminNetvaerksfejl, match="connectapi.garmin.com kan ikke slås op"):
        ig.login()


def test_login_forbindelsesfejl_er_netvaerk(garmin):
    garmin["exc"] = _rejst(GarminConnectConnectionError(f"Login failed: {DNS}"))
    with pytest.raises(ig.GarminNetvaerksfejl):
        ig.login()


def test_login_429_er_uaendret(garmin):
    garmin["exc"] = _rejst(GarminConnectTooManyRequestsError("429"))
    with pytest.raises(RuntimeError, match="HTTP 429"):
        ig.login()


def test_anden_fejl_sendes_videre_som_den_er(garmin):
    garmin["exc"] = _rejst(GarminConnectConnectionError("API Error 500 - intern fejl"))
    with pytest.raises(GarminConnectConnectionError, match="API Error 500"):
        ig.login()


def test_begge_er_runtimeerror_for_gamle_kaldere():
    assert issubclass(ig.GarminNetvaerksfejl, RuntimeError) and issubclass(ig.GarminLoginAfvist, RuntimeError)
