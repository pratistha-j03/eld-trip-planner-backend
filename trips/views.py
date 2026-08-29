from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Trip
from .serializers import TripSerializer
from .services.geocoding import GeocodingError, geocode
from .services.hos_planner import Leg, plan_trip
from .services.routing import RoutingError, get_route


@api_view(['GET'])
def health_check(request):
    return Response({'status': 'ok', 'service': 'eld-trip-planner-backend'})


class TripViewSet(viewsets.ModelViewSet):


    queryset = Trip.objects.all()
    serializer_class = TripSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()

        try:
            plan_payload = build_trip_plan(trip)
        except (GeocodingError, RoutingError) as exc:
            trip.delete()
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(plan_payload, status=status.HTTP_201_CREATED)


def build_trip_plan(trip):
    """Geocode -> route -> HOS plan -> combined JSON-ready dict for a Trip."""
    current = geocode(trip.current_location)
    pickup = geocode(trip.pickup_location)
    dropoff = geocode(trip.dropoff_location)

    route = get_route([current, pickup, dropoff])

    legs = [
        Leg(label='Drive to pickup', miles=route['legs'][0]['distance_miles'], hours=route['legs'][0]['duration_hours']),
        Leg(label='Drive to drop-off', miles=route['legs'][1]['distance_miles'], hours=route['legs'][1]['duration_hours']),
    ]
    plan = plan_trip(legs, float(trip.current_cycle_used_hours))

    return {
        'trip': TripSerializer(trip).data,
        'waypoints': [
            {'role': 'current', 'name': trip.current_location, **_coords(current)},
            {'role': 'pickup', 'name': trip.pickup_location, **_coords(pickup)},
            {'role': 'dropoff', 'name': trip.dropoff_location, **_coords(dropoff)},
        ],
        'route': {
            'distance_miles': round(route['distance_miles'], 1),
            'duration_hours': round(route['duration_hours'], 2),
            'geometry': route['geometry'],
        },
        'stops': plan.stops,
        'daily_logs': plan.daily_logs,
        'summary': {
            'total_days': plan.total_days,
            'total_miles': plan.total_miles,
            'total_driving_hours': plan.total_driving_hours,
        },
        'assumptions': plan.assumptions,
    }


def _coords(geocoded):
    return {'lat': geocoded['lat'], 'lon': geocoded['lon'], 'display_name': geocoded['display_name']}
