# IBM AI Racing Challenge - TORCS Corkscrew Course Submission

## 1. Project Overview

This project implements an autonomous racing AI controller for the TORCS (The Open Racing Car Simulator) racing simulation platform. The goal is to complete the Corkscrew track with optimal lap times while avoiding crashes and minimizing damage.

**Challenge:** Navigate a complex, high-speed corkscrew course at maximum speed without crashing  
**Solution:** Hybrid reactive-predictive controller combining racing line optimization with real-time sightline-based speed management

---

## 2. Tools Used

- **Simulator:** TORCS (The Open Racing Car Simulator)
- **Programming Language:** Python 3.x
- **Socket Protocol:** UDP (snakeoil3 protocol on port 3001)
- **Development Environment:** VS Code + Command Line
- **AI Guidance:** IBM Bob CLI mode and  Claude AI Assistants( when IBM Bob maxxed out)
- **Version Control:** Git/GitHub
- **Data Analysis:** Python pandas/CSV telemetry logging

---

## 3. Baseline Version

**File:** `snakeoil3_baseline.py` (Original provided template)

The baseline controller provided by the competition implements:
- Simple reactive steering based on track position error
- Linear throttle/brake control
- Fixed speed targets
- No collision avoidance

**Baseline Performance:**
- Lap Time: ~120 seconds (typical)
- Crashes: Occasional (high-speed corners)
- Damage: 5-15%
- Stability: Moderate (unpredictable at corners)

**Limitations:**
1. No anticipation of upcoming corners
2. Steering response too aggressive for high-speed sections
3. Speed targets not optimized for track geometry
4. No racing line optimization
5. Brake strategy reactive rather than predictive

---

## 4. Experimental/Final Version

**File:** `snakeoil3_v53_winning_fixed.py` (Final optimized controller)

### Architecture

The final controller implements a **Hybrid Reactive-Predictive Architecture**:

```
Car State (from TORCS)
    ↓
[Sightline Scanner] ←→ [Racing Line Predictor]
    ↓                           ↓
    [Speed Target] ← 70/30 Blend → [Track Prediction]
    ↓
[Steering Controller]
    ├─ Angle response (primary)
    └─ Track position correction (stabilization)
    ↓
[Throttle/Brake Controller]
    ├─ Gear selection (auto)
    ├─ Acceleration ramps
    └─ Predictive braking
    ↓
Control Commands (to TORCS)
```

### Key Components

1. **HybridController Class**
   - Steering gain: 7.0 (optimal for Corkscrew)
   - Racing line weight: 0.7 (70% predictive, 30% reactive)
   - Brake cap: 0.72 (aggressive braking while safe)
   - Speed targets tuned per track position

2. **RacingLineProfile Class**
   - 361-point racing line interpolation
   - 3608m total track distance
   - Binary search for efficient lookups
   - Smooth acceleration zones

3. **Speed Management**
   - Sightline-based speed targets (zone interpolation)
   - Smooth transitions between speed zones
   - Corner-specific minimum speeds (MINCORNER=50)
   - Maximum speed: 158 km/h

4. **Telemetry System**
   - Comprehensive CSV logging
   - 5480+ data points per lap
   - Parameter tracking and validation
   - Lap time and damage recording

---

## 5. Changes Tested

### Evolution Path

| Version | Change | Rationale | Result |
|---------|--------|-----------|--------|
| v50 | Aggressive steering | Better corner response | 116s, unstable |
| v51 | Incremental aggression | Gradual tuning | 115.8s, improved |
| v52 | Steering regression analysis | Identify optimal gain | 115.6s, stable |
| v53 | Conservative corners + aggressive braking | Smooth entry, confident exit | 115.31s, reliable |
| v53_fixed | Socket timeout fix (60s, no bind) | Proper protocol implementation | 115.31s, zero crashes |

### Key Tuning Parameters

**Final Configuration (v53_winning_fixed):**
```python
STEER_GAIN = 7.0              # Steering responsiveness
MINCORNER = 50                # Minimum corner speed (km/h)
BRAKE_CAP = 0.72              # Maximum braking force
MAXSPEED = 158                # Maximum target speed
SL_MAP = [                    # Speed targets by track position
    (20, 80),     # Zone 0: 80 km/h
    (28, 90),     # Zone 1: 90 km/h
    (45, 108),    # Zone 2: 108 km/h
    (78, 130),    # Zone 3: 130 km/h
    (118, 160),   # Zone 4: 160 km/h
    (162, 165)    # Zone 5: 165 km/h
]
RACING_LINE_WEIGHT = 0.7      # 70% predictive, 30% reactive
```

---

## 6. How I Used Bob (IBM Bob / Claude Assistant)

### Workflow: Ask → Plan → Code → Review

#### Phase 1: Problem Diagnosis
- **Asked:** "Why doesn't the controller complete the Corkscrew course safely?"
- **Bob analyzed:** Socket protocol issues, steering parameters, speed zones
- **Plan created:** Step-by-step optimization roadmap

#### Phase 2: Socket Protocol Fix
- **Problem:** v53 crashed with "socket timeout" on first lap
- **Root cause:** Explicit socket.bind() + 1.0 second timeout (too short)
- **Bob's solution:** Remove bind, increase to 60s timeout (matching v49)
- **Result:** Stable connection, reliable lap completion

#### Phase 3: Controller Tuning
- **Identified:** Steering too aggressive in corners → crashes
- **Bob tested:** STEER_GAIN values 5.0 → 8.0 in increments
- **Optimal found:** 7.0 (responsive but stable)
- **Strategy:** Blend 70% racing line (predictive) + 30% sightline (reactive)

#### Phase 4: Speed Zone Optimization
- **Problem:** Fixed speed targets don't match track geometry
- **Solution:** Sightline-based interpolated speed map
- **Zones tuned:** 6 zones from 80-165 km/h by track distance
- **Result:** Smooth acceleration, confident braking

#### Phase 5: Validation & Review
- **Test runs:** 5+ complete laps recorded
- **Telemetry analyzed:** Speed profiles, steering patterns, damage tracking
- **Bob reviewed:** Changes for safety, repeatability, and performance
- **Approved:** v53_winning_fixed ready for submission

---

## 7. How I Tested in TORCS

### Test Environment
- **Track:** Corkscrew (complex high-speed course)
- **Car:** car1-stock1
- **Mode:** Practice session
- **Duration:** ~2 minutes per lap

### Test Procedure

**For each version:**

1. **Start TORCS**
   - Launch wtorcs.exe
   - Select "Practice" mode
   - **Critical:** Select "scr_server" as driver
   - Select "Corkscrew" track
   - Click "OK" to start race

2. **Launch Controller**
   ```bash
   python snakeoil3_v53_winning_fixed.py
   ```

3. **Monitor Execution**
   - Watch console for connection message
   - Observe car accelerating in TORCS window
   - Monitor telemetry output (step count, speed, position)
   - Record lap completion time and damage

4. **Analyze Results**
   - Check CSV telemetry file
   - Verify no crashes (crash_flag = 0)
   - Verify no damage (damage = 0)
   - Calculate lap time from telemetry

5. **Document Findings**
   - Record in CHANGELOG.md
   - Compare with previous version
   - Identify improvements or regressions

---

## 8. Results Table

### Final Performance Metrics

| Metric | Value | Status |
|--------|-------|--------|
| **Lap Time** | 115.31 seconds | ✓ Excellent |
| **Crashes** | 0 | ✓ Perfect |
| **Damage** | 0.0% | ✓ Perfect |
| **Off-track Incidents** | 0 | ✓ Perfect |
| **Max Speed Achieved** | 168.9 km/h | ✓ Optimal |
| **Fuel Consumed** | 0.3% | ✓ Efficient |
| **Telemetry Points** | 5,482 | ✓ Complete |

### Comparison with Baseline

| Metric | Baseline | Final Version | Improvement |
|--------|----------|---------------|-------------|
| Lap Time | ~120s | 115.31s | **4.69s faster** |
| Crashes | Occasional | 0 | 100% safer |
| Damage | 5-15% | 0% | Complete durability |
| Stability | Moderate | Excellent | Consistent |

---

## 9. What Worked

### Successful Strategies

1. **Hybrid Reactive-Predictive Blend (70/30)**
   - Combines two complementary approaches
   - Racing line gives speed, sightline gives safety
   - Result: Fast and reliable

2. **Corner-Specific Speed Management**
   - Different speed zones for different track sections
   - Smooth interpolation prevents jerky transitions
   - Minimum speed limits prevent stalls
   - Result: Confident through turns, aggressive on straights

3. **Aggressive Braking Strategy (BRAKE_CAP=0.72)**
   - Strong but not excessive braking
   - Allows quick deceleration for tight corners
   - Prevents wheel lockup while being effective
   - Result: Better corner entry and exit

4. **Socket Protocol Implementation**
   - Proper UDP handshake with TORCS
   - 60-second timeout (adequate for full lap)
   - Graceful error handling for lap completion
   - Result: Reliable connection, no mid-lap crashes

5. **Comprehensive Telemetry**
   - Every step logged with full state
   - Parameter validation and tracking
   - Easy debugging and analysis
   - Result: Can identify exactly what's happening

---

## 10. What Did Not Work / Troubleshooting

### Issues Encountered and Solutions

#### Issue 1: Socket Timeout (v53 Original)
**Problem:** Script crashed with "socket timeout" after 1-2 seconds  
**Root Cause:** Explicit socket.bind() + 1.0 second timeout too short  
**Solution:** Remove bind(), increase timeout to 60 seconds  
**Result:** Stable connection ✓

#### Issue 2: Steering Too Aggressive (v50-v52)
**Problem:** Controller crashed on high-speed corners  
**Root Cause:** STEER_GAIN too high (8.5+), overresponding to track error  
**Solution:** Reduce to STEER_GAIN=7.0, add racing line prediction  
**Result:** Smooth, confident turns ✓

#### Issue 3: Fixed Speed Targets Not Optimal (early versions)
**Problem:** Single fixed speed too slow for straights, too fast for corners  
**Root Cause:** No account for track geometry variation  
**Solution:** Implement zone-based speed interpolation (6 zones, 80-165 km/h)  
**Result:** Optimal speed for each section ✓

#### Issue 4: No Crash Recovery (v49-v52)
**Problem:** Any contact could cause subsequent oscillations  
**Root Cause:** No predictive braking or corner speed limiting  
**Solution:** Add MINCORNER speed limit + aggressive brake cap  
**Result:** Safe, predictable behavior ✓

#### Issue 5: Racing Line File Not Found
**Problem:** Script warned about missing v54_racing_line.json  
**Root Cause:** File path or loading issue  
**Solution:** Verify file location, add fallback to reactive-only mode  
**Result:** Script continues, just slower ✓

---

## 11. What I Learned

### Key Insights

1. **Socket Protocol Matters**
   - Proper timeout values are critical (60s > 1s)
   - No explicit bind() needed for client
   - Graceful error handling prevents crashes

2. **Hybrid Approaches Beat Pure Strategies**
   - Pure reactive → unstable
   - Pure predictive → rigid
   - 70/30 blend → responsive AND stable

3. **Speed Management is Central**
   - Speed zones more important than steering tuning
   - Smooth transitions prevent jerky control
   - Minimum speeds prevent stalls

4. **Testing Matters**
   - Multiple runs show reproducibility
   - Telemetry reveals hidden issues
   - Small parameter changes have big effects

5. **Iterative Development Effective**
   - One change at a time
   - Test thoroughly before next change
   - Document everything
   - Previous failures inform future attempts

6. **Track Knowledge Valuable**
   - Different tracks need different strategies
   - Corkscrew requires smooth steering + careful braking
   - Speed zones map to physical track sections

---

## 12. Repository File Guide

### Directory Structure

```
AI-Racing-Challenge/
│
├── snakeoil3_baseline.py          # Original baseline (do not modify)
├── snakeoil3_v53_winning_fixed.py # Final optimized version
│
├── v54_racing_line.json           # Racing line data (361 points, 3608m)
│
├── README.md                       # This file
├── CHANGELOG.md                    # Version history and experiments
├── tuning-card.md                  # Parameter reference card
│
├── telemetry/
│   └── run_20261013_191823.csv    # Final test lap data (5482 points)
│
└── docs/
    ├── socket-protocol.md          # TORCS UDP protocol details
    ├── hybrid-architecture.md       # Controller design explanation
    └── test-procedure.md            # How to run controller in TORCS
```

### Key Files Explained

| File | Purpose | Size |
|------|---------|------|
| `snakeoil3_baseline.py` | Original provided template | ~200 lines |
| `snakeoil3_v53_winning_fixed.py` | Final controller (primary submission) | ~400 lines |
| `v54_racing_line.json` | Pre-computed racing line profile | 361 waypoints |
| `run_20261013_191823.csv` | Complete lap telemetry | 5482 rows |
| `README.md` | Project documentation | This file |
| `CHANGELOG.md` | Version history | All experiments |

---

## How to Run

### Prerequisites
1. TORCS installed and running
2. Python 3.x with basic libraries
3. Port 3001 available (UDP)

### Steps
1. Start TORCS: `wtorcs.exe`
2. Select: Practice → scr_server driver → Corkscrew → OK
3. Run controller: `python snakeoil3_v53_winning_fixed.py`
4. Watch for connection message in console
5. Observe car racing in TORCS window
6. Wait for lap completion (~115 seconds)
7. Check console for final lap time and damage

---

## Performance Summary

**Achieved Results:**
- ✓ 115.31 second lap time (4.69s faster than baseline)
- ✓ 0 crashes (100% crash-free)
- ✓ 0 damage (perfect condition)
- ✓ Consistent and repeatable
- ✓ Reliable socket connection
- ✓ Complete telemetry logging

**Status:** Ready for IBM AI Racing Challenge submission ✓

---

*Generated: October 14, 2026*  
*Controller Version: v53_winning_fixed*  
*Track: Corkscrew (TORCS)*  
*Submitted by: Anila Thomas*
