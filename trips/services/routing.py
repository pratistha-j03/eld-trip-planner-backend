
import requests

OSRM_BASE_URL = 'https://router.project-osrm.org/route/v1/driving/'
TIMEOUT_SECONDS = 15
METERS_PER_MILE = 1609.34


class RoutingError(Exception):
    pass


def get_route(waypoints):
    """
    waypoints: ordered list of {"lat": float, "lon": float} dicts (2+).
    Returns:
      {
        "distance_miles": float,
        "duration_hours": float,
        "geometry": <GeoJSON LineString>,
        "legs": [{"distance_miles": float, "duration_hours": float}, ...]
      }
    """
    if len(waypoints) < 2:
        raise RoutingError('At least two waypoints are required to route.')

    coords = ';'.join(f'{wp["lon"]},{wp["lat"]}' for wp in waypoints)
    url = f'{OSRM_BASE_URL}{coords}'

    try:
        response = requests.get(
            url,
            params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false'},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RoutingError(f'Could not reach the routing service: {exc}') from exc

    data = response.json()
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
    }
