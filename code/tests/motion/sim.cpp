// Simulated door lock for motion.h: thumb-turn with end stops, the dog clutch (teeth only drop in within +-4 deg of a
// slot), the reed magnet at the thumb-turn's home position, manual key turns and jams.
//   c++ -std=c++17 -Wall -o sim sim.cpp && ./sim

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "../../smart_lock/motion.h"

struct Lock {
  double thumb = 0;        // thumb-turn angle, 0 = home (key removable), +360 per locking turn
  double hub = 0;          // servo hub angle
  int servoDir = 0;
  bool clutchClosed = false;
  bool engaged = false;
  bool powered = false;
  double lowStop = -12;    // end stops just past home, as on a euro cylinder
  double highStop = 732;   // 2 turns to lock
  double speed = 360;      // deg/s under the motor (60 rpm)
  double alignedFor = 0;
  double play = 0;         // position of the teeth inside the slots, +-4 deg of backlash
} lock;

static void hwServo(int d) { lock.servoDir = d; }
static void hwClutch(bool c) { lock.clutchClosed = c; if (!c) lock.engaged = false; }
static void hwPower(bool on) { lock.powered = on; }

static bool reedActive() {
  double a = std::fmod(std::fmod(lock.thumb, 360) + 360, 360);
  return a < 12 || a > 348;
}

static bool aligned() {
  double d = std::fmod(std::fmod(lock.hub - lock.thumb, 60) + 60, 60);
  return d <= 4 || d >= 56;
}

static void step(double dt) {
  if (lock.clutchClosed && !lock.engaged) {
    lock.alignedFor = aligned() ? lock.alignedFor + dt : 0;
    if (lock.alignedFor >= 0.01) {  // SG90 pushes the teeth in
      lock.engaged = true;
      lock.play = std::remainder(lock.hub - lock.thumb, 60.0);
    }
  }
  if (!lock.powered || lock.servoDir == 0) return;
  double move = lock.servoDir * lock.speed * dt;
  if (lock.engaged) {
    // The hub turns freely inside the backlash, beyond it the thumb-turn has to follow
    double play = lock.play + move;
    double push = 0;
    if (play > 4) push = play - 4, play = 4;
    if (play < -4) push = play + 4, play = -4;
    double next = lock.thumb + push;
    if (next > lock.highStop || next < lock.lowStop) return;  // stalled against the end stop
    lock.thumb = next;
    lock.play = play;
  }
  lock.hub += move;
}

static int failures = 0;
static void expect(bool ok, const char* what) {
  printf("  %s %s\n", ok ? "ok  " : "FAIL", what);
  if (!ok) failures++;
}

static MotionController motion;
static unsigned long now = 0;

// Runs one movement to the end, returns the final result
static MotionResult run(bool toLocked) {
  motion.start(toLocked, now, reedActive());
  MotionResult result = MOTION_BUSY, last = MOTION_BUSY;
  while ((result = motion.update(now, reedActive())) != MOTION_IDLE) {
    if (result == MOTION_DONE || result == MOTION_JAMMED) last = result;
    step(0.001);
    now++;
    if (now > 120000000UL) break;
  }
  return last;
}

int main() {
  MotionHardware hw = {hwServo, hwClutch, hwPower};
  motion.begin(hw, true, 350, 40);

  printf("first lock, nothing learned yet (2 turn lock, clutch 51 deg off)\n");
  lock.hub = 51;
  MotionResult r = run(true);
  expect(r == MOTION_DONE, "finishes without a jam");
  expect(motion.learned.turnsToLock == 2, "learned 2 turns to lock");
  expect(motion.learned.revolutionMs > 900 && motion.learned.revolutionMs < 1300, "learned ~1 s per revolution");
  expect(lock.thumb > 700, "bolt fully thrown");

  printf("first unlock, learns the other direction\n");
  r = run(false);
  expect(r == MOTION_DONE && motion.learned.turnsToUnlock == 2, "learned 2 turns to unlock");
  expect(lock.thumb < 20, "back home");

  printf("normal lock after learning, clutch 51 deg off (key used before)\n");
  lock.hub = lock.thumb + 51;
  r = run(true);
  expect(r == MOTION_DONE, "done");
  expect(std::fabs(lock.thumb - 720) < 15, "stops at the magnet after 2 turns, not against the end stop");

  printf("unlock, then someone turned the key 100 deg and left it there\n");
  run(false);
  lock.thumb += 100;
  lock.hub = 13;
  r = run(true);
  expect(r == MOTION_DONE && std::fabs(lock.thumb - 720) < 15, "completes the turn and stops at home");

  printf("every clutch offset 0-59 deg after a key turn\n");
  bool all = true;
  double worst = 0;
  for (int offset = 0; offset < 60; offset++) {
    run(false);
    lock.hub = lock.thumb + offset;
    bool ok = run(true) == MOTION_DONE && std::fabs(lock.thumb - 720) < 15;
    worst = std::fmax(worst, std::fabs(lock.thumb - 720));
    all = all && ok;
  }
  printf("    worst end position error %.1f deg\n", worst);
  expect(all, "locks fully and stops at home for every offset");

  printf("jam: handle not lifted, the bolt blocks after 200 deg\n");
  run(false);
  lock.highStop = 200;
  r = run(true);
  expect(r == MOTION_JAMMED, "reports a jam");
  expect(lock.thumb <= 200, "stopped at the obstruction");
  lock.highStop = 732;
  run(false);

  printf("learning on a cylinder without an end stop gives up\n");
  motion.forget();
  lock.highStop = 1e9;
  lock.thumb = 0;
  r = run(true);
  expect(r == MOTION_JAMMED, "reports a problem instead of turning forever");
  expect(motion.learned.turnsToLock == 0, "nothing learned");

  printf("%s\n", failures ? "FAILED" : "ALL OK");
  return failures ? 1 : 0;
}
