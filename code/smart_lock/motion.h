// Motion controller
//
// Turns the thumb-turn until the reed sensor has seen the magnet the right number of times, instead of running the
// servo for a calibrated time. That makes the lock independent of servo speed, battery voltage and of how long the
// clutch needs to find its slots after the key was used (up to ~50 degrees of servo rotation).
//
// Nothing has to be calibrated by hand. When the number of turns for a direction is not known yet, the first move in
// that direction runs until the thumb-turn stops turning (the lock's end stop), counts the magnet passes on the way
// and stores them. If the magnet then doesn't come round in time on a later move, the lock reports a jam (e.g. the
// door handle wasn't lifted) instead of claiming to be locked.
//
// Plain C++ without Arduino calls, so it can be tested on a PC (code/tests/motion).

#pragma once

#include <stdint.h>

#define MOTION_MAX_TURNS 5             // a learning run that goes on longer than this means: no end stop, give up
#define MOTION_LEARN_STALL_MS 2500     // learning: the thumb-turn counts as stopped after this long without the magnet
#define MOTION_MIN_JAM_MS 1500         // shortest time we wait for the next magnet pass before reporting a jam
#define MOTION_ARRIVAL_DEBOUNCE_MS 150 // reed contact bounce / magnet lingering in front of the sensor

struct MotionLearned {
  uint8_t turnsToLock = 0;     // 0 = not learned yet
  uint8_t turnsToUnlock = 0;
  uint16_t revolutionMs = 0;   // one thumb-turn revolution under the motor, 0 = not learned yet
};

struct MotionHardware {
  void (*servo)(int direction);   // +1 lock, -1 unlock, 0 stop
  void (*clutch)(bool closed);
  void (*power)(bool on);         // servo power and "keep awake" on the battery board
};

enum MotionResult { MOTION_BUSY, MOTION_IDLE, MOTION_DONE, MOTION_JAMMED };

class MotionController {
public:
  MotionLearned learned;
  bool learnedChanged = false;    // set when a learning run stored new values, the sketch saves them

  void begin(const MotionHardware& hw, bool useClutch, unsigned long clutchSettleMs, unsigned long reliefMs) {
    _hw = hw;
    _useClutch = useClutch;
    _settleMs = useClutch ? clutchSettleMs : 0;
    _reliefMs = reliefMs;
  }

  bool busy() const { return _phase != IDLE; }
  bool targetLocked() const { return _toLocked; }
  bool learning() const { return _learning; }
  uint8_t arrivals() const { return _arrivals; }

  // Turns needed for a manual turn to count as a lock / unlock (the reed can't tell the direction)
  uint8_t manualTurns() const {
    uint8_t turns = learned.turnsToLock > learned.turnsToUnlock ? learned.turnsToLock : learned.turnsToUnlock;
    return turns > 0 ? turns : 1;
  }

  void forget() {
    learned = MotionLearned();
    learnedChanged = true;
  }

  bool start(bool toLocked, unsigned long now, bool reedActive) {
    if (_phase != IDLE) return false;
    _toLocked = toLocked;
    _target = toLocked ? learned.turnsToLock : learned.turnsToUnlock;
    _learning = _target == 0;
    _arrivals = 0;
    _jammed = false;
    _stopAt = 0;
    _reedWasActive = reedActive;
    _hw.power(true);
    if (_useClutch) _hw.clutch(true);
    _phase = ENGAGING;
    _phaseStart = now;
    return true;
  }

  // Call as often as possible while busy() with the current reed state
  MotionResult update(unsigned long now, bool reedActive) {
    unsigned long elapsed = now - _phaseStart;
    switch (_phase) {
      case IDLE:
        return MOTION_IDLE;

      case ENGAGING:
        if (elapsed >= _settleMs) {
          _hw.servo(_toLocked ? 1 : -1);
          enter(MOVING, now);
          _moveStart = now;
          _lastArrival = now;
          _firstArrival = 0;
        }
        return MOTION_BUSY;

      case MOVING: {
        bool arrived = reedActive && !_reedWasActive && now - _lastArrival >= MOTION_ARRIVAL_DEBOUNCE_MS;
        _reedWasActive = reedActive;
        if (arrived) {
          _arrivals++;
          if (_firstArrival == 0) _firstArrival = now;
          _lastArrival = now;
          // The reed closes a little before the magnet is centred: keep turning for ~1/30 of a revolution (12 deg)
          if (!_learning && _arrivals >= _target) _stopAt = now + learned.revolutionMs / 30 + 1;
          if (_learning && _arrivals > MOTION_MAX_TURNS) return stopMoving(now, true);
        }
        if (_stopAt != 0 && (long)(now - _stopAt) >= 0) return stopMoving(now, false);
        unsigned long sinceArrival = now - _lastArrival;
        if (_learning) {
          // The end stop: the magnet came round at least once, then the thumb-turn stopped
          if (_arrivals > 0 && sinceArrival >= MOTION_LEARN_STALL_MS) {
            storeLearned();
            return stopMoving(now, false);
          }
          if (_arrivals == 0 && sinceArrival >= 4UL * MOTION_LEARN_STALL_MS) return stopMoving(now, true);
        } else if (_stopAt == 0 && sinceArrival >= jamTimeout()) {
          return stopMoving(now, true);
        }
        return MOTION_BUSY;
      }

      case RELIEVING:
        if (elapsed >= _reliefMs) {
          _hw.servo(0);
          if (_useClutch) _hw.clutch(false);
          enter(RELEASING, now);
          return _jammed ? MOTION_JAMMED : MOTION_DONE;
        }
        return MOTION_BUSY;

      case RELEASING:
        // The thumb-turn may still swing back a little, the sensor is ignored for another second
        if (elapsed >= _settleMs + 1000) {
          _hw.power(false);
          enter(IDLE, now);
          return MOTION_IDLE;
        }
        return MOTION_BUSY;
    }
    return MOTION_IDLE;
  }

  unsigned long jamTimeout() const {
    // The first revolution can include the clutch finding its slots, allow two revolutions
    unsigned long timeout = 2UL * learned.revolutionMs + 600;
    return timeout > MOTION_MIN_JAM_MS ? timeout : MOTION_MIN_JAM_MS;
  }

private:
  enum Phase { IDLE, ENGAGING, MOVING, RELIEVING, RELEASING };
  Phase _phase = IDLE;
  MotionHardware _hw = {};
  bool _useClutch = false;
  unsigned long _settleMs = 0;
  unsigned long _reliefMs = 0;
  bool _toLocked = true;
  bool _learning = false;
  bool _jammed = false;
  bool _reedWasActive = false;
  uint8_t _target = 0;
  uint8_t _arrivals = 0;
  unsigned long _phaseStart = 0;
  unsigned long _moveStart = 0;
  unsigned long _lastArrival = 0;
  unsigned long _firstArrival = 0;
  unsigned long _stopAt = 0;

  void enter(Phase phase, unsigned long now) {
    _phase = phase;
    _phaseStart = now;
  }

  MotionResult stopMoving(unsigned long now, bool jammed) {
    _jammed = jammed;
    // Short reverse unloads the clutch teeth (and the end stop after a learning run)
    _hw.servo(_toLocked ? -1 : 1);
    enter(RELIEVING, now);
    return MOTION_BUSY;
  }

  void storeLearned() {
    if (_toLocked) learned.turnsToLock = _arrivals;
    else learned.turnsToUnlock = _arrivals;
    unsigned long revolution = _arrivals >= 2
      ? (_lastArrival - _firstArrival) / (_arrivals - 1)
      : _lastArrival - _moveStart;
    if (learned.revolutionMs == 0 || revolution < learned.revolutionMs) learned.revolutionMs = (uint16_t)revolution;
    learnedChanged = true;
  }
};
