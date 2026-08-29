

from dataclasses import dataclass, field

MILES_PER_METER = 1 / 1609.34

DUTY_OFF = 'OFF'
DUTY_SLEEPER = 'SB'
DUTY_DRIVING = 'D'
DUTY_ON_NOT_DRIVING = 'ON'

DUTY_LABELS = {
    DUTY_OFF: 'Off Duty',
    DUTY_SLEEPER: 'Sleeper Berth',
    DUTY_DRIVING: 'Driving',
    DUTY_ON_NOT_DRIVING: 'On Duty (Not Driving)',
}

FUEL_INTERVAL_MILES = 1000
FUEL_STOP_HOURS = 0.5
BREAK_AFTER_HOURS = 8
BREAK_DURATION_HOURS = 0.5
MAX_DRIVE_HOURS_PER_SHIFT = 11
MAX_ON_DUTY_WINDOW_HOURS = 14
OFF_DUTY_RESET_HOURS = 10
CYCLE_LIMIT_HOURS = 70
RESTART_HOURS = 34
PICKUP_DROPOFF_HOURS = 1
DAY_HOURS = 24

EPSILON = 1e-6


@dataclass
class Event:
    status: str
    start: float  # hours from trip start (clock 0)
    end: float
    label: str
    miles: float = 0.0  # only meaningful for driving events
    miles_marker: float = 0.0  # cumulative trip miles driven at the start of this event


@dataclass
class Leg:
    label: str
    miles: float
    hours: float


@dataclass
class TripPlan:
    events: list = field(default_factory=list)
    stops: list = field(default_factory=list)
    daily_logs: list = field(default_factory=list)
    total_days: int = 0
    total_driving_hours: float = 0.0
    total_miles: float = 0.0
    assumptions: list = field(default_factory=list)


def plan_trip(legs, current_cycle_used_hours):
    """
    legs: list[Leg] driven in order (e.g. current->pickup, pickup->dropoff)
    current_cycle_used_hours: hours already used in the 70hr/8day cycle
    """
    total_miles = sum(leg.miles for leg in legs)
    total_hours = sum(leg.hours for leg in legs)
    avg_speed = (total_miles / total_hours) if total_hours > EPSILON else 50.0

    state = _SimState(cycle_used=current_cycle_used_hours)
    events = []

    for i, leg in enumerate(legs):
        _drive_leg(leg, avg_speed, state, events)
        if i == 0:
            events.append(_advance(state, DUTY_ON_NOT_DRIVING, PICKUP_DROPOFF_HOURS, 'Pickup (loading)'))
        if i == len(legs) - 1:
            events.append(_advance(state, DUTY_ON_NOT_DRIVING, PICKUP_DROPOFF_HOURS, 'Drop-off (unloading)'))

    stops = [
        {
            'type': e.status,
            'label': e.label,
            'start_hour': round(e.start, 2),
            'end_hour': round(e.end, 2),
            'duration_hours': round(e.end - e.start, 2),
            'day': int(e.start // DAY_HOURS) + 1,
            'mile_marker': round(e.miles_marker, 1),
        }
        for e in events
        if e.status != DUTY_DRIVING
    ]

    daily_logs = _split_into_days(events, total_miles)

    plan = TripPlan(
        events=events,
        stops=stops,
        daily_logs=daily_logs,
        total_days=len(daily_logs),
        total_driving_hours=round(total_hours, 2),
        total_miles=round(total_miles, 1),
        assumptions=[
            'Trip is simulated starting at hour 0 of Day 1 (no real start time is collected).',
            'A single average speed derived from the route is used to place stops.',
            'Fuel stops take 30 minutes and also satisfy the 30-minute break requirement.',
            'Property-carrying driver, 70hrs/8days cycle, no adverse driving conditions.',
        ],
    )
    return plan


@dataclass
class _SimState:
    clock: float = 0.0
    cycle_used: float = 0.0
    drive_since_break: float = 0.0
    shift_drive_hours: float = 0.0
    shift_start_clock: float = 0.0
    miles_since_fuel: float = 0.0
    total_miles: float = 0.0


def _advance(state, status, duration, label, miles=0.0):
    marker = state.total_miles
    ev = Event(status=status, start=state.clock, end=state.clock + duration, label=label, miles=miles, miles_marker=marker)
    state.clock += duration
    if status == DUTY_DRIVING:
        state.total_miles += miles
    if status in (DUTY_DRIVING, DUTY_ON_NOT_DRIVING):
        state.cycle_used += duration
    return ev


def _start_new_shift(state):
    state.shift_start_clock = state.clock
    state.shift_drive_hours = 0.0
    state.drive_since_break = 0.0


def _drive_leg(leg, avg_speed, state, events):
    miles_remaining = leg.miles
    guard = 0
    while miles_remaining > EPSILON:
        guard += 1
        if guard > 100000:
            raise RuntimeError('HOS simulation did not converge \u2014 check inputs.')

        hours_to_leg_end = miles_remaining / avg_speed
        hours_to_break = max(BREAK_AFTER_HOURS - state.drive_since_break, 0)
        hours_to_shift_limit = max(MAX_DRIVE_HOURS_PER_SHIFT - state.shift_drive_hours, 0)
        hours_to_window_limit = max(MAX_ON_DUTY_WINDOW_HOURS - (state.clock - state.shift_start_clock), 0)
        hours_to_fuel = max((FUEL_INTERVAL_MILES - state.miles_since_fuel) / avg_speed, 0)
        hours_to_cycle_limit = max(CYCLE_LIMIT_HOURS - state.cycle_used, 0)

        drive_hours = min(
            hours_to_leg_end,
            hours_to_break,
            hours_to_shift_limit,
            hours_to_window_limit,
            hours_to_fuel,
            hours_to_cycle_limit,
        )

        if drive_hours > EPSILON:
            miles_this_stretch = drive_hours * avg_speed
            events.append(_advance(state, DUTY_DRIVING, drive_hours, leg.label, miles=miles_this_stretch))
            miles_remaining -= miles_this_stretch
            state.miles_since_fuel += miles_this_stretch
            state.drive_since_break += drive_hours
            state.shift_drive_hours += drive_hours

        if miles_remaining <= EPSILON:
            break

        # Whichever constraint is tightest determines the stop we take next.
        if drive_hours >= hours_to_cycle_limit - EPSILON:
            events.append(_advance(state, DUTY_OFF, RESTART_HOURS, '34-hour restart (cycle limit reached)'))
            state.cycle_used = 0.0
            _start_new_shift(state)
        elif drive_hours >= hours_to_shift_limit - EPSILON or drive_hours >= hours_to_window_limit - EPSILON:
            events.append(_advance(state, DUTY_OFF, OFF_DUTY_RESET_HOURS, '10-hour off-duty reset'))
            _start_new_shift(state)
        elif drive_hours >= hours_to_fuel - EPSILON:
            events.append(_advance(state, DUTY_ON_NOT_DRIVING, FUEL_STOP_HOURS, 'Fuel stop'))
            state.miles_since_fuel = 0.0
            state.drive_since_break = 0.0
        else:
            events.append(_advance(state, DUTY_OFF, BREAK_DURATION_HOURS, '30-minute break'))
            state.drive_since_break = 0.0


def _split_into_days(events, total_miles):
    if not events:
        return []

    last_end = max(e.end for e in events)
    total_days = max(1, int(last_end // DAY_HOURS) + (1 if last_end % DAY_HOURS > EPSILON else 0))

    days = []
    for day_index in range(total_days):
        day_start = day_index * DAY_HOURS
        day_end = day_start + DAY_HOURS
        segments = []
        miles_driven = 0.0

        for e in events:
            overlap_start = max(e.start, day_start)
            overlap_end = min(e.end, day_end)
            if overlap_end - overlap_start <= EPSILON:
                continue
            seg_hours = overlap_end - overlap_start
            seg_miles = 0.0
            if e.status == DUTY_DRIVING and (e.end - e.start) > EPSILON:
                seg_miles = e.miles * (seg_hours / (e.end - e.start))
                miles_driven += seg_miles
            segments.append({
                'status': e.status,
                'status_label': DUTY_LABELS[e.status],
                'start': round(overlap_start - day_start, 3),
                'end': round(overlap_end - day_start, 3),
                'label': e.label,
            })

        totals = {status: 0.0 for status in DUTY_LABELS}
        for seg in segments:
            totals[seg['status']] += seg['end'] - seg['start']

        days.append({
            'day': day_index + 1,
            'segments': segments,
            'totals': {DUTY_LABELS[k]: round(v, 2) for k, v in totals.items()},
            'total_hours_logged': round(sum(totals.values()), 2),
            'miles_driven': round(miles_driven, 1),
        })

    return days
