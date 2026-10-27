// Simulated door lock for motion.h (single servo + spiral coupling).
//
// Hub angle h (servo), thumb-turn angle k. The spiral lets q = h - k move freely between QMIN and QMAX
// (SPIRAL_TURNS * 360 deg); at the ends the hub drives the thumb-turn. The thumb-turn has end stops just past home
// after N turns. Knob reed: magnet at the thumb-turn's home. Hub hall: one magnet, placed (in the CAD) so that it
// passes the sensor 135 deg after reversing from either spiral end.
//   c++ -std=c++17 -Wall -o sim sim.cpp && ./sim

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "../../smart_lock/motion.h"

static const double S = MOTION_SPIRAL_TURNS * 360.0;
static const double QMAX = 400.0;              // arbitrary origin
static const double QMIN = QMAX - S;

struct Lock {
  double k = 0, h = QMAX - 135;
  int dir = 0;
  bool powered = false;
  int turns = 2;
  double blockAt = 1e9;                        // a jam: the bolt can't get past this thumb-turn angle
} lock;

static void hwServo(int d) { lock.dir = d; }
static void hwPower(bool on) { lock.powered = on; }

static double wrap(double a) { return std::remainder(a, 360.0); }
static bool knobActive() { return std::fabs(wrap(lock.k)) < 12; }
static bool hubActive() { return std::fabs(wrap(lock.h - (QMAX - 135))) < 8; }

static void step(double dt) {
  if (!lock.powered || lock.dir == 0) return;
  double q = lock.h - lock.k;
  bool pushing = (lock.dir > 0 && q >= QMAX - 1e-9) || (lock.dir < 0 && q <= QMIN + 1e-9);
  double speed = pushing ? 300 : 400;          // slower under load
  double move = lock.dir * speed * dt;
  if (!pushing) {
    double nq = q + move;
    if (nq > QMAX) { move = QMAX - q; }
    if (nq < QMIN) { move = QMIN - q; }
    lock.h += move;
    return;
  }
  double nk = lock.k + move;
  if (nk > lock.turns * 360 + 12 || nk < -12 || (lock.dir > 0 && nk > lock.blockAt)) return;  // stalled
  lock.k = nk;
  lock.h += move;
}

static int failures = 0;
static void expect(bool ok, const char* what) {
  if (!ok || getenv("VERBOSE")) printf("  %s %s\n", ok ? "ok  " : "FAIL", what);
  if (!ok) failures++;
}

static MotionController motion;
static unsigned long now = 0;

static MotionResult run(bool toLocked) {
  motion.start(toLocked, now, knobActive(), hubActive());
  MotionResult r, last = MOTION_BUSY;
  while ((r = motion.update(now, knobActive(), hubActive())) != MOTION_IDLE) {
    if (r == MOTION_DONE || r == MOTION_JAMMED) last = r;
    step(0.001);
    now++;
    if (now > 4000000000UL) break;
  }
  return last;
}

// Turning the key by hand: fails if the pin reaches the end of the spiral (the key would fight the servo)
static bool manual(double degrees) {
  double q = lock.h - (lock.k + degrees);
  if (q > QMAX || q < QMIN) return false;
  lock.k += degrees;
  return true;
}

static bool atHome(int turns) { return std::fabs(lock.k - turns * 360) < 15; }

int main() {
  MotionHardware hw = {hwServo, hwPower};
  motion.begin(hw);

  printf("first lock and unlock learn the turns (2 turn lock)\n");
  expect(run(true) == MOTION_DONE, "learning lock done");
  expect(motion.learned.turnsToLock == 2, "learned 2 turns to lock");
  expect(lock.k > 700, "bolt fully thrown");
  expect(manual(-720) && manual(720), "the key can unlock and lock by hand after parking");
  expect(run(false) == MOTION_DONE && motion.learned.turnsToUnlock == 2, "learning unlock, 2 turns");
  expect(atHome(0), "back home");
  printf("  learned %u ms per hub turn\n", motion.learned.revolutionMs);

  printf("normal moves stop at home and park with room for the key\n");
  expect(run(true) == MOTION_DONE && atHome(2), "lock stops at home after 2 turns");
  expect(manual(-720), "key unlocks by hand");
  expect(manual(720), "key locks again by hand");
  expect(run(false) == MOTION_DONE && atHome(0), "unlock");

  printf("random use: 300 operations, motor and key mixed\n");
  srand(1);
  bool locked = false, ok = true, keyOk = true;
  for (int i = 0; i < 300; i++) {
    if (rand() % 2) {
      MotionResult r = run(!locked);
      locked = !locked;
      ok = ok && r == MOTION_DONE && atHome(locked ? 2 : 0);
    } else {
      keyOk = keyOk && manual(locked ? -720 : 720);
      locked = !locked;
    }
  }
  expect(ok, "every motor move completed at home");
  expect(keyOk, "the key never had to fight the servo");

  printf("jam: the bolt blocks after 200 deg\n");
  if (locked) { run(false); locked = false; }
  lock.blockAt = 200;
  expect(run(true) == MOTION_JAMMED, "reported as jammed");
  expect(manual(-200), "after the jam the servo parked, the key turns freely");
  lock.blockAt = 1e9;

  printf("one-turn lock\n");
  motion.forget();
  lock.turns = 1;
  lock.k = 0;
  lock.h = QMAX - 135;
  expect(run(true) == MOTION_DONE && motion.learned.turnsToLock == 1, "learned 1 turn");
  expect(run(false) == MOTION_DONE && motion.learned.turnsToUnlock == 1 && atHome(0), "and back");
  bool oneOk = true;
  for (int i = 0; i < 50; i++) {
    oneOk = oneOk && run(true) == MOTION_DONE && manual(-360) && manual(360) && run(false) == MOTION_DONE && manual(360) && manual(-360);
  }
  expect(oneOk, "50 cycles with the key used in between");

  printf("fresh install: the pin can sit anywhere in the spiral\n");
  bool installOk = true;
  for (double q = QMIN; q <= QMAX; q += 45) {
    motion.forget();
    lock.turns = 2;
    lock.k = 0;
    lock.h = q;
    installOk = installOk && run(true) == MOTION_DONE && atHome(2) && manual(-720) && manual(720)
                && run(false) == MOTION_DONE && atHome(0) && manual(720) && manual(-720);
  }
  expect(installOk, "learns and works from every starting position");

  printf("%s\n", failures ? "FAILED" : "ALL OK");
  return failures ? 1 : 0;
}
