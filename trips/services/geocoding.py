
import requests

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'eld-trip-planner-assessment/1.0'
TIMEOUT_SECONDS = 10


class GeocodingError(Exception):
    pass


def geocode(location_name):

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={'q': location_name, 'format': 'json', 'limit': 1},
            headers={'User-Agent': USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f'Could not reach the geocoding service: {exc}') from exc

    results = response.json()
    if not results:
        raise GeocodingError(
            f'Could not find "{location_name}". Try a more specific value, e.g. "City, State".'
        )

    result = results[0]
    return {
        'lat': float(result['lat']),
        'lon': float(result['lon']),
        'display_name': result.get('display_name', location_name),
    }
