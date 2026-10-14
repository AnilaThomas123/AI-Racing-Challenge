#!/usr/bin/python
# snakeoil3_v53_winning_fixed.py
#
# CORKSCREW WINNING CONTROLLER (v53) - FIXED SOCKET COMMUNICATION
# Based on v49 socket architecture with v53 parameter set
# Best run achieved: 115.53 seconds (0 crashes, 0 damage, 0 off-track)
#
# KEY PARAMETERS FROM BEST RUN:
# MINCORNER: 50 km/h (conservative corner limiting)
# BRAKE_CAP: 0.72 (aggressive braking)
# SL_MAP: Zone-targeted speed (20,80)(28,90)(45,108)(78,130)(118,160)(162,165)
# STEER_GAIN: 7.0 (proven steering baseline)
#
# SOCKET FIX:
# - Removed explicit bind() to port 20001 (let OS assign dynamic port)
# - Changed timeout from 1.0s to 60.0s (match v49's working timeout)
# - Fixed init message format from custom to "SCR(init {angles})"
# - Added proper ServerState parser class

import socket
import sys
import getopt
import os
import time
import csv
import datetime
import math
from collections import defaultdict

PI = 3.14159265359
data_size = 2**17

# ========== ENHANCED RUN LOGGER FOR TELEMETRY ==========
class EnhancedRunLogger:
    """
    Logs telemetry data: speed, steering, braking, track position, damage, crashes, off-track
    """
    BACKWARD_GRACE = 3
    OFFTRACK_GRACE = 5

    def __init__(self, track_name='unknown', laps_attempted=1, parameters=None):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(script_dir, 'logs')
        os.makedirs(logs_dir, exist_ok=True)

        self.log_path = os.path.join(logs_dir, 'run_%s.csv' % timestamp)
        self.track_name = track_name
        self.laps_attempted = laps_attempted
        self.parameters = parameters or {}

        self._step = 0
        self._prev_damage = 0.0
        self._prev_last_lap_time = 0.0
        self._prev_speed = 0.0

        self.crash_count = 0
        self.off_track_count = 0
        self.backward_count = 0
        self.laps_completed = 0
        self.max_cur_lap_time = 0.0
        self.best_lap_time = float('inf')
        self.worst_lap_time = 0.0
        self.total_damage = 0.0
        self.max_speed_reached = 0.0
        self.min_speed_reached = float('inf')

        self.lap_times = []
        self.lap_damages = []
        self.lap_speeds = defaultdict(list)
        self.lap_start_step = 0
        self.current_lap = 1

        self._backward_streak = 0
        self._offtrack_streak = 0
        self._backward_active = False
        self._offtrack_active = False

        self._file = open(self.log_path, 'w', newline='')
        self._writer = csv.writer(self._file)

        self._writer.writerow([
            'step', 'lap', 'speed_x', 'speed_delta', 'speed_kmh',
            'angle', 'steer_cmd', 'track_pos', 'min_track_dist',
            'accel_cmd', 'brake_cmd', 'gear', 'damage', 'damage_delta', 'fuel',
            'cur_lap_time', 'last_lap_time',
            'backward_flag', 'offtrack_flag', 'crash_flag', 'lap_complete_flag'
        ] + ['track_%d' % i for i in range(19)])

        self._file.write('# PARAMETERS\n')
        for key, val in self.parameters.items():
            self._file.write('# param_%s,%s\n' % (key, val))
        self._file.write('# \n')

        print('[EnhancedRunLogger] Initialized')
        print('  Track: %s, Laps: %d' % (track_name, laps_attempted))
        print('  Parameters: %s' % self.parameters)
        print('  Log file: %s' % self.log_path)

    def record(self, S, R):
        self._step += 1
        speed_x = S.get('speedX', 0.0)
        angle = S.get('angle', 0.0)
        track_pos = S.get('trackPos', 0.0)
        track_sens = S.get('track', [0.0])
        min_track = min(track_sens) if isinstance(track_sens, list) else track_sens
        damage = S.get('damage', 0.0)
        fuel = S.get('fuel', 100.0)
        cur_lap_time = S.get('curLapTime', 0.0)
        last_lap_time = S.get('lastLapTime', 0.0)

        gear = R.get('gear', 1)
        accel = R.get('accel', 0.0)
        brake = R.get('brake', 0.0)
        steer = R.get('steer', 0.0)

        speed_delta = speed_x - self._prev_speed
        damage_delta = damage - self._prev_damage

        self.max_speed_reached = max(self.max_speed_reached, speed_x)
        if speed_x > 0:
            self.min_speed_reached = min(self.min_speed_reached, speed_x)
        self.lap_speeds[self.current_lap].append(speed_x)

        crash_flag = 1 if damage_delta > 0 else 0
        if crash_flag:
            self.crash_count += 1
        self._prev_damage = damage
        self.total_damage = damage
        self._prev_speed = speed_x

        backward_detected = S.get('backwardCount', 0) > self._prev_last_lap_time
        self._prev_last_lap_time = S.get('backwardCount', 0)

        offtrack_flag = 1 if abs(track_pos) > 1.0 else 0
        if offtrack_flag:
            self._offtrack_streak += 1
        else:
            self._offtrack_streak = 0
        if self._offtrack_streak >= self.OFFTRACK_GRACE:
            self.off_track_count += 1

        lap_complete = 1 if cur_lap_time < last_lap_time and last_lap_time > 0 else 0
        if lap_complete:
            self.laps_completed += 1
            self.lap_times.append(last_lap_time)
            self.best_lap_time = min(self.best_lap_time, last_lap_time)
            self.worst_lap_time = max(self.worst_lap_time, last_lap_time)
            self.lap_damages.append(damage)
            self.current_lap += 1

        row = [
            self._step, self.current_lap, speed_x, speed_delta, speed_x * 3.6,
            angle, steer, track_pos, min_track,
            accel, brake, gear, damage, damage_delta, fuel,
            cur_lap_time, last_lap_time,
            backward_detected, offtrack_flag, crash_flag, lap_complete
        ] + list(track_sens)

        self._writer.writerow(row)
        self._file.flush()

    def close(self):
        self._file.close()
        print('[EnhancedRunLogger] Summary:')
        print('  Total crashes: %d' % self.crash_count)
        print('  Total off-track: %d' % self.off_track_count)
        print('  Total laps completed: %d' % self.laps_completed)
        print('  Best lap time: %.2f s' % self.best_lap_time if self.lap_times else 'N/A')
        print('  Total damage: %.2f' % self.total_damage)
        print('  Max speed: %.1f km/h' % (self.max_speed_reached * 3.6))
        print('  Log saved to: %s' % self.log_path)

# ================ CLIENT (SOCKET FIX) ================
class Client():
    def __init__(self, H='localhost', p=3001, t='unknown'):
        self.host = H
        self.port = p
        self.socket = None
        self.maxSteps = 0
        self.curStep = 0
        self.S = ServerState()
        self.R = DriverAction()
        self.track_name = t

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # FIXED: Don't bind to port - let OS assign dynamic port for client communication
        # self.socket.bind(('0.0.0.0', p))  # <-- REMOVED THIS LINE (was causing timeout)
        self.socket.settimeout(60.0)  # FIXED: Increased from 1.0 to 60.0 seconds
        self.so = None

        # Send initialization message to TORCS (required handshake)
        self._send_init_message()

    def _send_init_message(self):
        """Send initialization message to TORCS to start communication"""
        try:
            angles = "-45 -19 -12 -7 -4 -2.5 -1.7 -1 -.5 0 .5 1 1.7 2.5 4 7 12 19 45"
            initmsg = f"SCR(init {angles})"  # FIXED: Proper SCR format instead of custom format
            self.socket.sendto(initmsg.encode(), (self.host, self.port))
        except Exception as e:
            print(f"Warning: Failed to send init message: {e}")

    def get_servers_input(self):
        try:
            self.so, _ = self.socket.recvfrom(data_size)
            # Decode bytes to string for parsing
            if isinstance(self.so, bytes):
                self.so = self.so.decode('utf-8')
            self.S = ServerState(self.so)
        except socket.timeout:
            self.so = None
            return False
        return True

    def respond_to_server(self):
        if self.so is not None:
            self.socket.sendto(self.R.__repr__().encode(), (self.host, self.port))

    def shutdown(self):
        if self.socket:
            self.socket.close()

# ================ PARSER ================
class ServerState():
    def __init__(self, server_string=''):
        self.d = {}
        self.server_string = server_string
        self.parse(server_string)

    def parse(self, server_string=''):
        self.servstr= server_string.strip()[:-1]
        sslisted= self.servstr.strip().lstrip('(').rstrip(')').split(')(')
        for i in sslisted:
            w= i.split(' ')
            self.d[w[0]]= destringify(w[1:])

    def __repr__(self):
        out= str()
        for k in sorted(self.d):
            strout= str(self.d[k])
            if type(self.d[k]) is list:
                strlist= [str(i) for i in self.d[k]]
                strout= ', '.join(strlist)
            out+= "%s: %s\n" % (k,strout)
        return out

class DriverAction():
    def __init__(self):
       self.actionstr= str()
       self.d= { 'accel':0.2, 'brake':0, 'clutch':0, 'gear':1, 'steer':0,
                'focus':[-90,-45,0,45,90], 'meta':0 }

    def clip_to_limits(self):
        self.d['steer']= clip(self.d['steer'], -1, 1)
        self.d['brake']= clip(self.d['brake'], 0, 1)
        self.d['accel']= clip(self.d['accel'], 0, 1)
        self.d['clutch']= clip(self.d['clutch'], 0, 1)
        if self.d['gear'] not in [-1, 0, 1, 2, 3, 4, 5, 6]:
            self.d['gear']= 0
        if self.d['meta'] not in [0,1]:
            self.d['meta']= 0
        if type(self.d['focus']) is not list or min(self.d['focus'])<-180 or max(self.d['focus'])>180:
            self.d['focus']= 0

    def __repr__(self):
        self.clip_to_limits()
        out= str()
        for k in self.d:
            out+= '('+k+' '
            v= self.d[k]
            if not type(v) is list:
                out+= '%.3f' % v
            else:
                out+= ' '.join([str(x) for x in v])
            out+= ')'
        return out

def clip(v,lo,hi):
    if v<lo: return lo
    elif v>hi: return hi
    else: return v

def destringify(s):
    if not s: return s
    if type(s) is str:
        try:
            return float(s)
        except ValueError:
            print("Could not find a value in %s" % s)
            return s
    elif type(s) is list:
        if len(s) < 2:
            return destringify(s[0])
        else:
            return [destringify(i) for i in s]

# ========== DRIVE FUNCTION (V53: WINNING PARAMETERS) ==========
def drive_example(c):
    S, R = c.S.d, c.R.d

    # Reset brake each frame (it must not persist from the previous frame)
    R['brake'] = 0.0
    if 'accel' not in R:
        R['accel'] = 0.2

    # ===================== V53 WINNING PARAMETERS (115.53s BEST) =====================
    STEER_GAIN   = 7.0     # Proven steering baseline
    MAXSPEED     = 158     # km/h
    MINCORNER    = 50      # CONSERVATIVE: corners speed-limited to 50 km/h max
    FAR_CLEAR    = 150.0   # m of forward clearance => full MAXSPEED
    NEAR_CLEAR   = 18.0    # m of forward clearance => slow to MINCORNER
    BRAKE_CAP    = 0.72    # AGGRESSIVE: strong braking capacity (v49: 0.58, v53: 0.72)
    BRAKE_GAIN   = 0.042   # brake harder per km/h overshoot
    ACCEL_GAIN   = 0.10    # accel per km/h of speed deficit
    # ==================================================================================

    speed = S.get('speedX', 0.0)
    track = S.get('track', None)
    track_pos = S.get('trackPos', 0.0)

    # ---- Simple center-line steering ----
    R['steer'] = (S.get('angle', 0.0) * STEER_GAIN / PI) - track_pos * 0.55
    if R['steer'] > 1.0:  R['steer'] = 1.0
    if R['steer'] < -1.0: R['steer'] = -1.0

    # ---- Corner-aware lookahead: sightline -> target, WITH STABILITY GUARDS ----
    if isinstance(track, list) and len(track) >= 19:
        arc = [track[i] for i in range(3, 16)]        # -7..+7 deg (narrower = less peeking)
        raw_sightline = max((v for v in arc if v is not None), default=FAR_CLEAR)
        if raw_sightline < 0:
            raw_sightline = 0.0
    else:
        raw_sightline = FAR_CLEAR

    # GUARD 1 - Sightline smoothing (0.60_old/0.40_new for responsiveness)
    if not hasattr(c, '_sl'):
        c._sl = raw_sightline
    c._sl = 0.60 * c._sl + 0.40 * raw_sightline
    sightline = c._sl

    def _interp(x, pts):
        if x <= pts[0][0]:  return pts[0][1]
        if x >= pts[-1][0]: return pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return pts[-1][1]

    # V53 SL_MAP: Zone-targeted speed (from best run telemetry)
    SL_MAP = ((20.0, 80.0), (28.0, 90.0), (45.0, 108.0),
              (78.0, 130.0), (118.0, 160.0), (162.0, 165.0))
    target_raw = _interp(sightline, SL_MAP)

    # V34 HARD CAP (sharp-corner protector)
    if isinstance(track, list) and len(track) >= 19:
        straight = min(track[8], track[9], track[10])
        if straight < 0:
            straight = 0.0
    else:
        straight = FAR_CLEAR
    HARD = ((11.0, 60.0), (17.0, 72.0), (28.0, 92.0), (50.0, 128.0), (85.0, 158.0))
    hardcap = _interp(straight, HARD)
    if target_raw > hardcap:
        target_raw = hardcap

    # GUARD 2 - STEER GATE: never aim for high speed while still turning hard.
    steer_mag = abs(R['steer'])
    gate = MAXSPEED - (MAXSPEED - MINCORNER) * min(1.0, steer_mag / 0.62)
    if target_raw > gate:
        target_raw = gate

    # GUARD 3 - RATE-LIMIT: target can fall fast (braking) but rise only gradually
    if not hasattr(c, '_tgt'):
        c._tgt = target_raw
    delta = target_raw - c._tgt
    if delta > 1.5:
        delta = 1.5           # rise <= 1.5 km/h per frame (~75 km/h per sec)
    elif delta < -20.0:
        delta = -20.0         # allow quick drop for braking
    c._tgt += delta
    target = c._tgt

    # ---- Throttle / Brake from speed error, decoupled from steering ----
    if speed < target:
        R['accel'] = min(1.0, 0.30 + (target - speed) * ACCEL_GAIN)
        R['brake'] = 0.0
    else:
        over = speed - target
        brake = min(BRAKE_CAP, over * BRAKE_GAIN)
        # Ease brake when steering hard: avoid front-wheel lockup / understeer
        brake *= (1.0 - 0.6 * min(1.0, abs(R['steer'])))
        R['brake'] = brake
        R['accel'] = 0.0

    # ---- Launch assist from a near stop ----
    if speed < 10:
        R['accel'] = 1.0
        R['brake'] = 0.0

    # ---- Traction control: back off throttle on rear wheelspin ----
    wsv = S.get('wheelSpinVel', None)
    if isinstance(wsv, list) and len(wsv) >= 4:
        if (wsv[2] + wsv[3]) - (wsv[0] + wsv[1]) > 5:
            R['accel'] *= 0.8

    # ---- Transmission (speedX is km/h) ----
    R['gear'] = 1
    if speed > 50:  R['gear'] = 2
    if speed > 80:  R['gear'] = 3
    if speed > 110: R['gear'] = 4
    if speed > 140: R['gear'] = 5
    if speed > 170: R['gear'] = 6

    return

# ================ MAIN ================
if __name__ == "__main__":
    track_name = 'unknown'
    host = 'localhost'
    port = 3001
    max_steps = 100000

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ['-t', '--track']:
            if i + 1 < len(sys.argv):
                track_name = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        elif arg in ['-p', '--port']:
            if i + 1 < len(sys.argv):
                try:
                    port = int(sys.argv[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                i += 1
        elif arg in ['-H', '--host']:
            if i + 1 < len(sys.argv):
                host = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        elif arg in ['-m', '--steps']:
            if i + 1 < len(sys.argv):
                try:
                    max_steps = int(sys.argv[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                i += 1
        else:
            i += 1

    C = Client(H=host, p=port, t=track_name)
    C.maxSteps = max_steps

    # V53 WINNING PARAMETERS
    driver_params = {
        'controller': 'v53_winning',
        'strategy': 'Conservative corners + aggressive braking: MINCORNER 50, BRAKE_CAP 0.72, SL_MAP zone-targeted',
        'MAXSPEED': 158,
        'MINCORNER': 50,
        'BRAKE_CAP': 0.72,
        'STEER_GAIN': 7.0,
        'SL_MAP_targets': '(20,80)(28,90)(45,108)(78,130)(118,160)(162,165)',
        'best_time_achieved': '115.53s',
        'conditions': '0 crashes, 0 damage, 0 off-track'
    }

    logger = EnhancedRunLogger(
        track_name=track_name,
        laps_attempted=1,
        parameters=driver_params
    )

    for step in range(max_steps, 0, -1):
        try:
            C.get_servers_input()
        except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
            print(f"[Controller] Connection closed by TORCS (normal end-of-lap): {type(e).__name__}")
            break

        if C.so is None:
            break
        drive_example(C)
        C.respond_to_server()
        if C.S and C.R:
            logger.record(C.S.d, C.R.d)

    C.shutdown()
    logger.close()
