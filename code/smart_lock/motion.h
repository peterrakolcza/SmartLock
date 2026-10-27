// Motion controller for the single-servo spiral coupling
//
// The servo hub and the thumb-turn are joined by a spiral (scroll) lost-motion coupling: a pin on the thumb-turn
// side runs in a spiral groove under the hub. Inside the spiral (~2.75 turns) the two turn independently, so the key
// and the thumb-turn turn freely. Only at the ends of the spiral does the hub drive the thumb-turn.
//
// A movement:
//   1. DRIVING   the servo turns; first it takes up the free play, then it turns the thumb-turn until the knob reed
//                has seen the magnet the learned number of times (thumb-turn at its home position)
//   2. PARKING   the servo turns back the learned turns + 1 hub-magnet passes, which leaves the pin in the spiral
//                with room for the key to undo the movement by hand
//
// Sensors: the knob reed (magnet in the thumb-turn adapter, as before) and a hub sensor (hall switch, magnet in the
// hub) that counts hub revolutions. The hub sensor also detects a stall: no hub pass in time = end stop or jam.
//
// Nothing to calibrate: the first lock and the first unlock run until the thumb-turn stops at its end stop and learn
// the number of turns from the knob reed.
//
// Plain C++ without Arduino calls, tested on a PC in code/tests/motion.

#pragma once

#include <stdint.h>

#define MOTION_DEBOUNCE_MS 120        // sensor bounce / magnet lingering in front of the sensor
#ifndef MOTION_DEFAULT_REV_MS
#define MOTION_DEFAULT_REV_MS 1200    // hub revolution time until learned (v5's worm drive sets its own)
#endif
#define MOTION_MAX_TURNS 5            // learning: more knob turns than this means no end stop, give up
#define MOTION_SPIRAL_TURNS 2.75f     // free play of the coupling (the CAD's SPIRAL_TURNS)

struct MotionLearned {
  uint8_t turnsToLock = 0;     // 0 = not learned yet
  uint8_t turnsToUnlock = 0;
  uint16_t revolutionMs = 0;   // one hub revolution under load, 0 = not learned yet
};

struct MotionHardware {
  void (*servo)(int direction);   // +1 lock, -1 unlock, 0 stop
  void (*power)(bool on);
};

enum MotionResult { MOTION_BUSY, MOTION_IDLE, MOTION_DONE, MOTION_JAMMED };

class MotionController {
public:
  MotionLearned learned;
  bool learnedChanged = false;

  void begin(const MotionHardware& hw) { _hw = hw; }

  bool busy() const { return _phase != IDLE; }
  bool targetLocked() const { return _toLocked; }
  bool learning() const { return _learning; }
  uint8_t arrivals() const { return _knobArrivals; }

  uint8_t manualTurns() const {
    uint8_t turns = learned.turnsToLock > learned.turnsToUnlock ? learned.turnsToLock : learned.turnsToUnlock;
    return turns > 0 ? turns : 1;
  }

  void forget() {
    learned = MotionLearned();
    learnedChanged = true;
  }

  bool start(bool toLocked, unsigned long now, bool knobActive, bool hubActive) {
    if (_phase != IDLE) return false;
    _toLocked = toLocked;
    _target = toLocked ? learned.turnsToLock : learned.turnsToUnlock;
    _learning = _target == 0;
    _knobArrivals = 0;
    _hubArrivals = 0;
    _jammed = false;
    _stopAt = 0;
    _knobWas = knobActive;
    _hubWas = hubActive;
    _lastKnob = now;
    _lastHub = now;
    _firstHub = 0;
    _hw.power(true);
    _hw.servo(toLocked ? 1 : -1);
    enter(DRIVING, now);
    return true;
  }

  // Call as often as possible while busy()
  MotionResult update(unsigned long now, bool knobActive, bool hubActive) {
    bool knobArrived = edge(knobActive, _knobWas, _lastKnob, now);
    bool hubArrived = edge(hubActive, _hubWas, _lastHub, now);

    switch (_phase) {
      case IDLE:
        return MOTION_IDLE;

      case DRIVING: {
        if (hubArrived) {
          if (_firstHub != 0) learnRevolution(now - _prevHub);
          if (_firstHub == 0) _firstHub = now;
          _prevHub = now;
          _hubArrivals++;
        }
        if (knobArrived) {
          _knobArrivals++;
          // The reed closes a little before the magnet is centred: run on ~12 deg
          if (!_learning && _knobArrivals >= _target) _stopAt = now + revolution() / 30 + 1;
        }
        if (_stopAt != 0 && (long)(now - _stopAt) >= 0) return finishDrive(now, false);

        // The hub stopped turning: the thumb-turn is against its end stop (learning) or something blocks it (jam)
        if (now - _lastHub > stallTimeout()) {
          if (_learning && _knobArrivals > 0 && _knobArrivals <= MOTION_MAX_TURNS) {
            if (_toLocked) learned.turnsToLock = _knobArrivals;
            else learned.turnsToUnlock = _knobArrivals;
            learnedChanged = true;
            return finishDrive(now, false);
          }
          return finishDrive(now, true);
        }
        // Too many hub turns: knob sensor broken, or no end stop while learning
        unsigned maxHub = (_learning ? MOTION_MAX_TURNS : _target) + (unsigned)MOTION_SPIRAL_TURNS + 2;
        if (_hubArrivals > maxHub || (_learning && _knobArrivals > MOTION_MAX_TURNS)) return finishDrive(now, true);
        return MOTION_BUSY;
      }

      case PARKING:
        if (hubArrived) {
          _hubArrivals++;
          if (_hubArrivals >= _parkPasses && _stopAt == 0) _stopAt = now + revolution() / 36 + 1;
        }
        if (_stopAt != 0 && (long)(now - _stopAt) >= 0) {
          _hw.servo(0);
          enter(SETTLING, now);
          return MOTION_BUSY;
        }
        if (now - _phaseStart > (unsigned long)(_parkPasses + 2) * revolution() * 2) {
          // The hub sensor never came round: stop anyway, the next move takes up whatever is left
          _hw.servo(0);
          enter(SETTLING, now);
        }
        return MOTION_BUSY;

      case SETTLING:
        if (now - _phaseStart >= 300) {
          _hw.power(false);
          enter(IDLE, now);
          return MOTION_IDLE;
        }
        return MOTION_BUSY;
    }
    return MOTION_IDLE;
  }

  unsigned long revolution() const { return learned.revolutionMs ? learned.revolutionMs : MOTION_DEFAULT_REV_MS; }
  unsigned long stallTimeout() const { return 2 * revolution() + 400; }
  uint8_t parkPasses() const { return _parkPasses; }

private:
  enum Phase { IDLE, DRIVING, PARKING, SETTLING };
  Phase _phase = IDLE;
  MotionHardware _hw = {};
  bool _toLocked = true;
  bool _learning = false;
  bool _jammed = false;
  bool _knobWas = false;
  bool _hubWas = false;
  uint8_t _target = 0;
  uint8_t _knobArrivals = 0;
  uint8_t _hubArrivals = 0;
  uint8_t _parkPasses = 0;
  unsigned long _phaseStart = 0;
  unsigned long _lastKnob = 0;
  unsigned long _lastHub = 0;
  unsigned long _firstHub = 0;
  unsigned long _prevHub = 0;
  unsigned long _stopAt = 0;

  void enter(Phase phase, unsigned long now) {
    _phase = phase;
    _phaseStart = now;
  }

  // Magnet arriving at a sensor; a re-trigger within the debounce time is contact bounce
  static bool edge(bool active, bool& was, unsigned long& last, unsigned long now) {
    if (active == was) return false;
    was = active;
    if (!active || now - last < MOTION_DEBOUNCE_MS) return false;
    last = now;
    return true;
  }

  void learnRevolution(unsigned long revolution) {
    if (revolution < 300 || revolution > 5000) return;
    if (learned.revolutionMs == 0 || revolution < learned.revolutionMs) {
      learned.revolutionMs = (uint16_t)revolution;
      learnedChanged = true;
    }
  }

  MotionResult finishDrive(unsigned long now, bool jammed) {
    _jammed = jammed;
    // Park: back off the driven turns + 1 hub-magnet passes, so the key can undo this movement by hand
    uint8_t turns = _toLocked ? learned.turnsToLock : learned.turnsToUnlock;
    _parkPasses = (turns > 0 ? turns : 1) + 1;
    _hubArrivals = 0;
    _stopAt = 0;
    _hw.servo(_toLocked ? -1 : 1);
    enter(PARKING, now);
    return jammed ? MOTION_JAMMED : MOTION_DONE;
  }
};
