import math
import ssl

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OSRM_BASE_URL = 'https://router.project-osrm.org/route/v1/driving/'
TIMEOUT_SECONDS = 15
METERS_PER_MILE = 1609.34
EARTH_RADIUS_MILES = 3958.8
FALLBACK_AVG_SPEED_MPH = 55.0


class RoutingError(Exception):
    pass


class _ModernTLSAdapter(HTTPAdapter):

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs['ssl_context'] = ctx
        return super().proxy_manager_for(*args, **kwargs)


def _build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=0.6,
        status_forcelist=[502, 503, 504],
        allowed_methods=['GET'],
    )
    adapter = _ModernTLSAdapter(max_retries=retry)
    session.mount('https://', adapter)
    return session


def _haversine_miles(lat1, lon1, lat2, lon2):
    to_rad = math.radians
    d_lat = to_rad(lat2 - lat1)
    d_lon = to_rad(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return EARTH_RADIUS_MILES * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _straight_line_route(waypoints):
    legs = []
    coordinates = [[waypoints[0]['lon'], waypoints[0]['lat']]]
    total_miles = 0.0

    for a, b in zip(waypoints, waypoints[1:]):
        miles = _haversine_miles(a['lat'], a['lon'], b['lat'], b['lon'])
        hours = miles / FALLBACK_AVG_SPEED_MPH
        legs.append({'distance_miles': miles, 'duration_hours': hours})
        coordinates.append([b['lon'], b['lat']])
        total_miles += miles

    return {
        'distance_miles': total_miles,
        'duration_hours': sum(leg['duration_hours'] for leg in legs),
        'geometry': {'type': 'LineString', 'coordinates': coordinates},
        'legs': legs,
        'estimated': True,
    }


def get_route(waypoints):

    if len(waypoints) < 2:
        raise RoutingError('At least two waypoints are required to route.')

    coords = ';'.join(f'{wp["lon"]},{wp["lat"]}' for wp in waypoints)
    url = f'{OSRM_BASE_URL}{coords}'

    session = _build_session()
    try:
        response = session.get(
            url,
            params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false'},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return _straight_line_route(waypoints)

    if data.get('code') != 'Ok' or not data.get('routes'):
        raise RoutingError(f'Routing failed: {data.get("message", data.get("code", "unknown error"))}')

    route = data['routes'][0]
    return {
        'distance_miles': route['distance'] / METERS_PER_MILE,
        'duration_hours': route['duration'] / 3600,
        'geometry': route['geometry'],
        'legs': [
            {
                'distance_miles': leg['distance'] / METERS_PER_MILE,
                'duration_hours': leg['duration'] / 3600,
            }
            for leg in route['legs']
        ],
        'estimated': False,
    }