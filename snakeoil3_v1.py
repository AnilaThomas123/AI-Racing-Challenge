#!/usr/bin/env python
"""
V54 HYBRID CONTROLLER: Reactive + Predictive Racing Line Blend
INTEGRATED VERSION: Loads precomputed racing line from v54_racing_line.json

Architecture:
1. PREDICTIVE LAYER: Precomputed racing line from V53 telemetry
   - Track position targets indexed by lap distance
   - Speed targets by track geometry (Adriano's approach)
   - Smooth, lookahead-aware control signals

2. REACTIVE LAYER: V53's sightline-based corrections
   - Real-time sightline distance mapping to speed targets
   - Deviation detection and steering corrections
   - Safety fallback for blind corners

3. HYBRID BLEND:
   - Use precomputed line as primary target when visibility is good
   - Use sightline as adaptive safety cap
   - Blend steering: ideal_steer + correction * position_error
   - Speed: min(ideal_speed, sightline_speed * safety_factor)
"""

import math
import json
import os

class RacingLineProfile:
    """In-memory racing line profile loaded from precomputed JSON."""

    def __init__(self, track_length_m=3608):
        self.track_length = track_length_m
        self.profile = {}  # distance_m -> {track_pos, ideal_speed, ...}
        self.distances = []  # sorted keys for interpolation

    def load_from_json(self, json_path):
        """Load racing line profile from precomputed JSON."""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            # Parse profile: keys are strings, convert to floats
            for dist_str, profile_data in data['racing_line'].items():
                distance_m = float(dist_str)
                self.profile[distance_m] = profile_data

            self.distances = sorted(self.profile.keys())
            print(f"[V54] Loaded racing line profile: {len(self.profile)} points, {self.distances[-1]:.0f}m total")
            return True
        except Exception as e:
            print(f"[V54] Failed to load racing line: {e}")
            return False

    def get(self, distance_m):
        """Lookup profile at given distance with interpolation."""
        if not self.profile:
            return None

        # Clamp to track length
        distance_m = distance_m % self.track_length

        if not self.distances:
            return None

        if distance_m <= self.distances[0]:
            return self.profile[self.distances[0]]
        if distance_m >= self.distances[-1]:
            return self.profile[self.distances[-1]]

        # Binary search for nearest lower distance
        for i, d in enumerate(self.distances[:-1]):
            if self.distances[i] <= distance_m < self.distances[i+1]:
                d1, d2 = self.distances[i], self.distances[i+1]
                p1, p2 = self.profile[d1], self.profile[d2]

                # Linear interpolation blend
                blend = (distance_m - d1) / (d2 - d1) if d2 > d1 else 0

                return {
                    'track_pos': p1['track_pos'] * (1 - blend) + p2['track_pos'] * blend,
                    'ideal_speed': p1['ideal_speed'] * (1 - blend) + p2['ideal_speed'] * blend,
                    'angle_change': p1['angle_change'] * (1 - blend) + p2['angle_change'] * blend,
                    'samples': p1['samples'],
                }

        return self.profile[self.distances[-1]]


class HybridController:
    """V54 Hybrid: Predictive racing line + reactive sightline blend."""

    def __init__(self):
        # V53's proven stable parameters (reverting V52 failure)
        self.STEER_GAIN = 7.0
        self.MINCORNER = 50
        self.BRAKE_CAP = 0.72

        # V53's zone-targeted SL_MAP (aggressive distribution)
        self.SL_MAP = [
            (20.0, 82.0),   # Tight corners: conservative +5
            (28.0, 92.0),   # Opening: conservative +6
            (45.0, 111.0),  # Curves: moderate +7
            (78.0, 135.0),  # Long curves: aggressive +9
            (118.0, 162.0), # Straights: moderate +7
            (162.0, 165.0), # Far straights: capped
        ]

        # Hybrid tuning parameters
        self.RACING_LINE_WEIGHT = 0.7  # How much to trust precomputed line (vs sightline)
        self.SIGHTLINE_SAFETY_CAP = 1.0  # Sightline as speed cap multiplier

        # Racing line profile (loaded from JSON)
        self.racing_line = None

        # State tracking
        self.sightline_smooth = 100.0
        self.last_speed_target = 0.0

    def set_racing_line(self, profile):
        """Set the racing line profile."""
        self.racing_line = profile

    def _interp(self, distance, table):
        """Interpolate table lookup."""
        if not table or distance < table[0][0]:
            return table[0][1] if table else 0

        for i in range(len(table) - 1):
            d1, v1 = table[i]
            d2, v2 = table[i + 1]
            if distance <= d2:
                if d2 == d1:
                    return v1
                blend = (distance - d1) / (d2 - d1)
                return v1 + blend * (v2 - v1)

        return table[-1][1]

    def drive(self, carstate):
        """
        HYBRID CONTROL LOOP:
        1. Get ideal controls from precomputed racing line (predictive)
        2. Get adaptive controls from sightline (reactive)
        3. Blend them intelligently
        4. Apply safety guards
        """
        R = {'steer': 0, 'accel': 1.0, 'brake': 0, 'gear': 1, 'clutch': 0}

        angle = carstate.angle
        track_pos = carstate.trackPos
        speed_x = carstate.speedX
        speed_kmh = speed_x * 3.6

        # === LAYER 1: STEERING ===
        # Base steering from angle + track position (always used)
        R['steer'] = (angle * self.STEER_GAIN / math.pi) - track_pos * 0.55

        # === LAYER 2: SIGHTLINE (Reactive) ===
        # Get focus and range sensors
        sensors = carstate.track
        focus = sensors[9] if len(sensors) > 9 else 200

        # Smooth sightline
        self.sightline_smooth = 0.60 * self.sightline_smooth + 0.40 * focus

        # Sightline -> speed mapping (V53's zone-targeted approach)
        sightline_target = self._interp(self.sightline_smooth, self.SL_MAP)

        # === LAYER 3: PREDICTIVE RACING LINE ===
        # Estimate current lap distance (from cur_lap_time and speed estimate)
        estimated_distance = (speed_kmh / 3.6) * carstate.curLapTime
        estimated_distance = estimated_distance % 3608  # Normalize to lap

        ideal_profile = None
        ideal_steer = None
        ideal_speed = 150  # Default if racing line unavailable

        if self.racing_line:
            ideal_profile = self.racing_line.get(estimated_distance)
            if ideal_profile:
                # Ideal track position from precomputed line
                ideal_track_pos = ideal_profile['track_pos']
                ideal_speed = ideal_profile['ideal_speed'] * 0.95  # Conservative 95% of peak

                # Steering correction to follow ideal line
                position_error = track_pos - ideal_track_pos
                # Reduce correction in straights (angle_change < 0.01)
                if ideal_profile['angle_change'] > 0.01:
                    ideal_steer = (angle * self.STEER_GAIN / math.pi) - ideal_track_pos * 0.55
                    R['steer'] = R['steer'] * 0.5 + ideal_steer * 0.5 + position_error * 0.3

        # === LAYER 4: SPEED BLENDING ===
        # Primary: Use ideal racing line speed when visible
        # Secondary: Cap with sightline safety
        # Fallback: Use sightline if racing line unavailable

        if ideal_speed and self.racing_line:
            # Blend: prefer ideal line but bounded by sightline
            speed_target = ideal_speed * self.RACING_LINE_WEIGHT + sightline_target * (1 - self.RACING_LINE_WEIGHT)
            # Cap with sightline safety margin
            speed_target = min(speed_target, sightline_target * self.SIGHTLINE_SAFETY_CAP)
        else:
            # Fallback: pure sightline control (reactive)
            speed_target = sightline_target

        # Rate limiting (V53's proven rates)
        delta = speed_target - self.last_speed_target
        if delta > 1.5:
            delta = 1.5
        elif delta < -20.0:
            delta = -20.0
        speed_target = self.last_speed_target + delta
        self.last_speed_target = speed_target

        # === LAYER 5: PEDAL CONTROL ===
        # Throttle/brake from speed error
        speed_error = speed_target - speed_kmh

        # Braking
        R['brake'] = 0
        if speed_error < -0.5:
            # Need to brake
            brake_mag = min(0.8, abs(speed_error) / 10.0)
            # Ease off brake based on steering (can't brake hard mid-corner)
            brake_ease = 1.0 - 0.6 * min(1.0, abs(R['steer']))
            R['brake'] = brake_mag * brake_ease
            R['brake'] = min(self.BRAKE_CAP, R['brake'])
            R['accel'] = 0
        else:
            # Throttle
            accel_mag = min(1.0, speed_error / 10.0)
            # Reduce throttle at full lock
            accel_gate = 1.0 - 0.8 * min(1.0, abs(R['steer']))
            R['accel'] = accel_mag * accel_gate
            R['accel'] = max(0, min(1.0, R['accel']))

        # === GEAR SHIFTING ===
        thresholds = [50, 80, 110, 140, 170]
        current_gear = carstate.gear

        for threshold in thresholds:
            if speed_kmh > threshold and current_gear == carstate.gear:
                current_gear += 1

        for i in range(len(thresholds) - 1, -1, -1):
            if speed_kmh < thresholds[i] - 10 and current_gear > 1:
                current_gear -= 1

        R['gear'] = max(1, min(6, current_gear))

        return R


def drive(carstate):
    """Main entry point for TORCS."""
    global controller, racing_line_loaded

    # Initialize on first call
    if not hasattr(drive, 'controller'):
        drive.controller = HybridController()
        drive.racing_line_loaded = False

        # Try to load racing line profile (only once)
        if not drive.racing_line_loaded:
            # Look for profile in current directory
            if os.path.exists('v54_racing_line.json'):
                profile = RacingLineProfile()
                if profile.load_from_json('v54_racing_line.json'):
                    drive.controller.set_racing_line(profile)
                    drive.racing_line_loaded = True
                    print(f"[V54] Racing line loaded from v54_racing_line.json")

            if not drive.racing_line_loaded:
                print("[V54] WARNING: Racing line profile not found. Running in reactive-only mode.")

    # Get control signals
    R = drive.controller.drive(carstate)

    return R
