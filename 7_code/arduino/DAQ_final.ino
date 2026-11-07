// =====================================================================
// PV-TEG-PCM hybrid energy harvester - data acquisition sketch
// Arduino Mega 2560. M.Y.A. Perera, S/20472, University of Peradeniya.
//
// DOCUMENTATION VERSION. Compared with the sketch that logged the data,
// only comments, a few Serial text messages and the (unused) constant
// BPW_PULLDOWN_OHMS were corrected so that the sketch agrees with the
// thesis. No logic, pin number, timing value or logged column changed.
// Corrected: BPW34 resistor value (1.32 kOhm, not 9.87 kOhm), TEG MOSFET
// pin (8, not 10, in the comments and messages), dwell time (50 ms, not
// 100 ms) and sweep duration (about 40 s, not 12.8 s) in the comments.
// =====================================================================

#include <Wire.h>
#include <stdio.h>
#include <SPI.h>
#include <SD.h>
#include <RTClib.h>              // install "RTClib" by Adafruit (for the DS3231)
#include <Adafruit_INA219.h>
#include <Adafruit_ADS1X15.h>    // install "Adafruit ADS1X15" library
#include <max6675.h>             // install "MAX6675" by Adafruit (for the 8 thermocouples)

// IMPORTANT: all I2C boards share the same bus and MUST have distinct
// addresses. INA219s default to 0x40; solder/bridge the A0 pad to shift
// to 0x41 (as used here), A1 pad -> 0x44, both -> 0x45, etc.
// The ADS1115 defaults to 0x48 with its ADDR pin tied to GND.
// The DS3231 RTC is fixed at 0x68 and shares the same SDA/SCL lines.
Adafruit_INA219 ina219_1(0x40);  // PV panel 1 (hybrid), load switched by MOSFET on pin 5
Adafruit_INA219 ina219_2(0x41);  // PV panel 2 (bare), load switched by MOSFET on pin 12
Adafruit_ADS1115 ads_teg;        // TEG channel (load MOSFET on pin 8) + BPW channel, I2C addr 0x48
RTC_DS3231 rtc;                  // I2C addr 0x68, SDA/SCL shared with the boards above

// ---------------- microSD card module (SPI) ----------------
// Wire the module's SPI lines to the Mega's hardware SPI pins:
//   MOSI -> 51, MISO -> 50, SCK -> 52, plus 5V/3.3V (check your module) and GND.
// CS can be any free digital pin - defaulting to 53 (the Mega's hardware SS
// pin) since it isn't used elsewhere in this sketch. Change it here if you
// wire CS somewhere else.
const int SD_CS_PIN = 53;
bool sdReady = false;   // set in setup(); every SD write is skipped if this is false
bool rtcReady = false;  // set in setup(); falls back to a millis()-based timestamp if false

// Filenames are date-stamped from the RTC (see setup()) so each day's data
// lands in its own file. Kept as mutable String (not const char*) because
// they're computed at runtime, once, from rtc.now(). NOTE: computed ONCE at
// boot (power-on) - if the board stays running across midnight, it keeps
// writing to the boot-day's file rather than rolling over at midnight. If
// the board is restarted during the day, new rows are appended to the same
// file (the name is the same) and the "Sweep N" marker numbering starts
// again at 1. Fallback names below are only used if the RTC isn't found at
// all.
// Classic SD library needs 8.3 names: "V" + MMDD + ".CSV" = 5 chars, fits.
String voltLogFileName = "VOLTLOG.CSV";  // recurring (1min) voltage+temperature readings
String sweepLogFileName = "SWEEP.CSV";   // PWM sweep readings

// Full header for VOLTLOG.CSV, used both for the Serial banner and the file
// itself so the two can never drift out of sync with each other.
const char* VOLT_HEADER =
  "Timestamp,PWM,V1(V),I1(mA),P1(mW),V2(V),I2(mA),P2(mW),V_TEG(V),I_TEG(mA),P_TEG(mW),V_BPW(V),"
  "TC1(C),TC2(C),TC3(C),TC4(C),TC5(C),TC6(C),TC7(C),TC8(C)";

// ---------------- 8x MAX6675 thermocouples (software SPI) ----------------
// Isolated-bus wiring, now extended further: TC2, TC3 and TC4 each get
// their OWN dedicated SO pin too (they used to share pin 46 along with
// TC1 and TC5). Only TC1 and TC5 now share the pin-46 SO line between
// just the two of them - every other channel (TC2, TC3, TC4, TC6, TC7,
// TC8) is fully isolated. This is the same bus-contention fix as before,
// just applied to three more channels: giving a chip its own SO line
// means its clone board's imperfect tri-stating can never fight another
// chip's output on a shared wire. SCK is still shared by all 8 (safe to
// share - it's a clock the Mega always actively drives, never fought
// over). None of these pins are the Mega's hardware SPI pins, so the
// MAX6675 library bit-bangs them all in software.
//
//   SCK (shared by all 8)          -> pin 48
//   SO / MISO (shared, TC1 & TC5)  -> pin 46
//   SO / MISO (TC2, isolated)      -> pin 35
//   SO / MISO (TC3, isolated)      -> pin 36
//   SO / MISO (TC4, isolated)      -> pin 37
//   SO / MISO (TC6, isolated)      -> pin 32
//   SO / MISO (TC7, isolated)      -> pin 33
//   SO / MISO (TC8, isolated)      -> pin 34
//   CS: TC1..TC5                   -> pins 40..44, respectively
//   CS: TC6..TC8                   -> pins 22, 23, 24
//
// NOTE: pins 20/21 were avoided for CS6-8 even though they're numerically
// close to 22-24, because 20/21 are the Mega's hardware I2C bus (SDA/SCL)
// used by the INA219s, ADS1115, and DS3231 RTC via Wire.begin() -
// repurposing them as CS outputs would break I2C entirely. Pins 35/36/37
// were picked for TC2/TC3/TC4 because they're plain, unused GPIO pins on
// the Mega - not the hardware SPI pins (50/51/52/53), not I2C (20/21),
// not any PWM pin already in use (5/8/12), and not already claimed by
// TC6-TC8's SO lines (32/33/34) or the SD card's CS (53).
const int NUM_THERMOCOUPLES = 8;
const int TC_SCK_PIN = 48;
const int TC_SO_PIN = 46;   // shared SO for TC1 & TC5 only
const int TC2_SO_PIN = 35;  // TC2's own, isolated SO line
const int TC3_SO_PIN = 36;  // TC3's own, isolated SO line
const int TC4_SO_PIN = 37;  // TC4's own, isolated SO line
const int TC6_SO_PIN = 32;  // TC6's own, isolated SO line
const int TC7_SO_PIN = 33;  // TC7's own, isolated SO line
const int TC8_SO_PIN = 34;  // TC8's own, isolated SO line
const uint8_t TC_CS_PINS[NUM_THERMOCOUPLES] = { 40, 41, 42, 43, 44, 22, 23, 24 };

MAX6675 thermocouples[NUM_THERMOCOUPLES] = {
  MAX6675(TC_SCK_PIN, TC_CS_PINS[0], TC_SO_PIN),    // TC1 - shared SO (with TC5)
  MAX6675(TC_SCK_PIN, TC_CS_PINS[1], TC2_SO_PIN),   // TC2 - DEDICATED, isolated SO
  MAX6675(TC_SCK_PIN, TC_CS_PINS[2], TC3_SO_PIN),   // TC3 - DEDICATED, isolated SO
  MAX6675(TC_SCK_PIN, TC_CS_PINS[3], TC4_SO_PIN),   // TC4 - DEDICATED, isolated SO
  MAX6675(TC_SCK_PIN, TC_CS_PINS[4], TC_SO_PIN),    // TC5 - shared SO (with TC1)
  MAX6675(TC_SCK_PIN, TC_CS_PINS[5], TC6_SO_PIN),   // TC6 - DEDICATED, isolated SO
  MAX6675(TC_SCK_PIN, TC_CS_PINS[6], TC7_SO_PIN),   // TC7 - DEDICATED, isolated SO
  MAX6675(TC_SCK_PIN, TC_CS_PINS[7], TC8_SO_PIN)    // TC8 - DEDICATED, isolated SO
};

const int pwmPin1 = 5;    // PV1 load MOSFET gate (IRF540N); PWM-capable on virtually all boards
const int pwmPin2 = 12;   // PV2 load MOSFET gate (IRF540N); PWM-capable on Mega; NOT on Uno/Nano (use 3,6,9,10,11 there)
const int pwmPinTEG = 8;  // TEG load MOSFET gate (IRLZ44N); PWM-capable on Uno/Nano/Mega alike

int currentPWM = 0;      // held PWM value between sweeps - always 0 (MOSFET OFF); see runSweep()
bool running = false;
unsigned long lastRead = 0; // global so runSweep() can resync it too
const unsigned long RECURRING_INTERVAL_MS = 1UL * 60UL * 1000UL; // 1 minute between recurring readings

// ---------------- Auto-sweep scheduling ----------------
// "start" now runs an initial sweep immediately, then begins recurring
// 1-minute readings once that sweep finishes. From then on, a sweep is
// triggered automatically every AUTO_SWEEP_INTERVAL_MS, measured
// START-to-START (i.e. the gap is timed from when one sweep began to when
// the next one begins, NOT from when one finishes to when the next
// starts) - 15 minutes. lastSweepStartMillis is stamped at the top of
// runSweep() itself, so it's updated no matter what triggered that sweep
// (auto-schedule, "start", or a manual "sweep" command).
//
// Between sweeps, the MOSFET is always held OFF (PWM=0) during recurring
// readings - the sweep loop itself is the only time PWM goes non-zero.
// sweepCount increments once per sweep (of any trigger) and is used to
// stamp a "Sweep N" marker row into the sweep log right before each
// sweep's own data rows, so repeated sweeps landing in that same file
// over a long session can still be told apart.
unsigned long lastSweepStartMillis = 0;
const unsigned long AUTO_SWEEP_INTERVAL_MS = 15UL * 60UL * 1000UL; // 15 minutes
unsigned int sweepCount = 0;

// ---------------- TEG measurement config (ADS1115 + 1.3 ohm shunt) ----------------
//   A0 = TEG string's free positive terminal (same node as MOSFET drain) -> V_TEG.
//   A1 = junction between the MOSFET source and the top of the 1.3 ohm shunt,
//        whose OTHER leg goes to GND. V(A1) IS the shunt voltage already -
//        do NOT take a differential A0-A1 reading here.
//   A2 = BPW photodiode (e.g. BPW34) light-sensor signal.
//   A3 is not used in this wiring.
const float SHUNT_RESISTANCE_TEG = 1.3; // ohms, measured with a multimeter
const adsGain_t TEG_GAIN = GAIN_TWOTHIRDS; // +/-6.144V full scale, used for A0/A1/A2 alike

// ---------------- BPW photodiode channel config (ADS1115 A2) ----------------
// Photoconductive mode: 5V -> BPW34 cathode, anode -> node -> six 220 ohm
// resistors in series (1.32 kilohm in all) -> GND, node -> ADS1115 A2.
// More light => higher V(A2). The sketch only logs the voltage at A2; this
// constant is NOT used in any calculation (it is for reference only, e.g.
// photocurrent = V_BPW / BPW_PULLDOWN_OHMS when processing the data).
const float BPW_PULLDOWN_OHMS = 1320.0; // 6 x 220 ohm = 1.32 kilohm - for reference/logging only

// ---------------- Sweep config (separate "sweep" command) ----------------
// Sweeps the PWM held on all three pins across a range, dwelling at each
// step, and at each step reads PV panel 1 (INA219 #1), PV panel 2 (INA219
// #2), the TEG (ADS1115 A0 voltage + A1 shunt -> current), AND the BPW
// photodiode (ADS1115 A2) back-to-back. Fixed defaults:
// full 0-255 range, step 1 (every single PWM value), 50ms dwell per step.
// (The dwell alone adds up to 12.8 s per sweep; with the readings and the
// writing of each row to Serial and the SD card, one step takes about
// 155 ms and a whole sweep about 40 s.)
// Periodic (1-minute) voltage+temperature logging is suppressed for the
// duration (running is temporarily cleared) and NOT written to the voltage
// log while a sweep is in progress - the 8 thermocouples are NOT read
// during a sweep either, since that read only happens inside the same
// suppressed block.
// Only the sweep log grows during a sweep. See runSweep()'s resumeRunning
// parameter for what happens to running/stopped state once it finishes.
const int SWEEP_START_DEFAULT = 0;
const int SWEEP_END_DEFAULT = 255;
const int SWEEP_STEP_DEFAULT = 1;
const unsigned long SWEEP_DWELL_MS_DEFAULT = 50; // settle time per step, in ms

// ---------------- Standalone/outdoor auto-start ----------------
// For field use with a power bank and no laptop/Serial monitor: this many
// milliseconds after power-on, setup() automatically does exactly what
// typing "start" over Serial would do (see doStart()), and the sweep +
// recurring-read + auto-sweep cycle already in loop() then keeps the whole
// thing running on its own, continuously, until power is cut. Nothing
// about the Serial command interface is disabled - a laptop can still be
// plugged in at any time to watch the log or send stop/set/sweep - this
// just removes the requirement to ever do that.
const unsigned long BOOT_DELAY_MS = 20000; // 20 seconds after power-on

// Does everything "start" is supposed to do: flips running on and fires
// the initial sweep. Shared by the "start" Serial command AND the
// automatic post-boot auto-start, so the two can never drift out of sync.
void doStart() {
  running = true;
  Serial.println("STARTED. Running initial sweep now - recurring 1-minute readings (MOSFET held at PWM=0 between sweeps) begin once it completes...");
  // resumeRunning=true: unlike a mid-session "sweep" command (which
  // restores whatever state was active before it), this very first sweep
  // must ALWAYS leave the system running afterward, since that's the whole
  // point of "start". This also stamps lastSweepStartMillis, kicking off
  // the 15-minute start-to-start auto-sweep schedule.
  runSweep(SWEEP_START_DEFAULT, SWEEP_END_DEFAULT, SWEEP_STEP_DEFAULT, SWEEP_DWELL_MS_DEFAULT, true);
}

void setup() {
  Serial.begin(9600);
  Wire.begin();

  if (!ina219_1.begin()) {
    Serial.println("Failed to find INA219 #1 (0x40)");
    while (1) { delay(10); }
  }
  if (!ina219_2.begin()) {
    Serial.println("Failed to find INA219 #2 (0x41) - check address jumper on second board");
    while (1) { delay(10); }
  }
  if (!ads_teg.begin(0x48)) {
    Serial.println("Failed to find ADS1115 for TEG/BPW (0x48) - check wiring/ADDR pin");
    while (1) { delay(10); }
  }
  ads_teg.setGain(TEG_GAIN);

  // ---- DS3231 RTC ----
  // Non-fatal if missing: readings/logging still work, just with a
  // millis()-based fallback timestamp instead of a wall-clock one.
  if (rtc.begin()) {
    rtcReady = true;
    if (rtc.lostPower()) {
      // RTC lost its backup battery / is brand new - seed it with the
      // sketch's compile time. Re-upload (or add your own 'settime'
      // command) any time you need to correct it afterwards.
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
      Serial.println("RTC lost power - time set to compile time. Adjust later if needed.");
    }
  } else {
    Serial.println("Failed to find DS3231 RTC - continuing with millis()-based timestamps instead.");
  }

  // ---- Build date-stamped log filenames from the RTC, once, at boot ----
  // 8.3-safe: "V"+MMDD+".CSV" / "S"+MMDD+".CSV" (5-char name + 3-char ext).
  // Only possible if the RTC is present - if not, voltLogFileName /
  // sweepLogFileName just keep their static VOLTLOG.CSV / SWEEP.CSV
  // fallback values declared above, since there's no wall-clock date to
  // stamp them with otherwise. NOTE: computed once here at boot, so a
  // board left running across midnight keeps writing to the boot-day's
  // file rather than rolling over - re-run "start" the next day (or just
  // power-cycle) to pick up the new date.
  if (rtcReady) {
    DateTime bootNow = rtc.now();
    char voltName[13];
    char sweepName[13];
    snprintf(voltName, sizeof(voltName), "V%02d%02d.CSV", bootNow.month(), bootNow.day());
    snprintf(sweepName, sizeof(sweepName), "S%02d%02d.CSV", bootNow.month(), bootNow.day());
    voltLogFileName = String(voltName);
    sweepLogFileName = String(sweepName);
  }
  Serial.print("Voltage log file: ");
  Serial.println(voltLogFileName);
  Serial.print("Sweep log file: ");
  Serial.println(sweepLogFileName);

  // ---- microSD card ----
  // Also non-fatal: if the card is missing/unreadable, we just skip all
  // file writes and keep working over Serial only.
  if (SD.begin(SD_CS_PIN)) {
    sdReady = true;
    Serial.println("SD card ready.");
  } else {
    Serial.println("SD card init failed - logging to file is DISABLED (check card/wiring/CS pin).");
  }

  pinMode(pwmPin1, OUTPUT);
  pinMode(pwmPin2, OUTPUT);
  pinMode(pwmPinTEG, OUTPUT);
  analogWrite(pwmPin1, 0);   // stay off until told to start
  analogWrite(pwmPin2, 0);
  analogWrite(pwmPinTEG, 0);

  Serial.println("Triple Static PWM Hold Test Ready (PV1/PV2 via INA219 + TEG & BPW via ADS1115 + 8x TC via MAX6675, SD+RTC logging).");
  Serial.println("Commands (optional - see auto-start below):");
  Serial.println("  start       -> run an initial sweep immediately, then begin recurring 1-minute");
  Serial.println("                readings (MOSFET held at PWM=0) once that sweep finishes. From");
  Serial.println("                then on, a sweep auto-repeats every 15 minutes, timed START-to-START;");
  Serial.println("                each sweep is preceded by a 'Sweep N' marker row in the sweep log.");
  Serial.println("  stop        -> set all PWM outputs to 0, pause readings AND the auto-sweep schedule");
  Serial.println("  set <value> -> change held PWM value (0-255) for ALL THREE pins at once, e.g. 'set 150'");
  Serial.println("  sweep [start end step dwellMs] -> run a sweep on demand (also resets the 15-min");
  Serial.println("                auto-sweep timer), logging PV1+PV2+TEG (V/I/P each) + BPW to the");
  Serial.println("                sweep CSV, then restore whatever running/stopped state was active before.");
  Serial.println("                Defaults: full 0-255 range, step 1, 50ms dwell per step.");
  Serial.println("                e.g. 'sweep' (uses defaults) or 'sweep 0 255 1 50'");
  Serial.println("Type a command and press Enter - or just leave it powered: it auto-starts");
  Serial.println("on its own (see below) and needs no commands at all in the field.");

  // ---- Standalone/outdoor auto-start ----
  // No Serial monitor needed here or after this point. Two stages:
  //  1) A fixed BOOT_DELAY_MS (20s) settle delay, always, regardless of
  //     the RTC - simple power-on grace period.
  //  2) THEN, if the RTC is working, wait until its seconds reads exactly
  //     0 - i.e. the next real clock full minute (e.g. 15:30:43 -> wait
  //     until 15:31:00) - before doing exactly what "start" does. Starting
  //     sweep 1 on a clean minute boundary means every later 1-minute
  //     recurring reading and 15-minute sweep (both timed off millis()
  //     from this exact moment, and re-aligned to the RTC again after
  //     every single sweep - see runSweep()) also lands on a clean minute
  //     mark, instead of drifting by however long each sweep took.
  //
  // If the RTC isn't available, there's no wall-clock second to align to,
  // so step 2 is skipped and it just starts right after the boot delay.
  Serial.print("Waiting ");
  Serial.print(BOOT_DELAY_MS / 1000);
  Serial.println("s after power-on before auto-starting...");
  delay(BOOT_DELAY_MS);

  if (rtcReady) {
    Serial.println("Now waiting for the next full minute (RTC seconds = 00), then auto-starting...");
    while (rtc.now().second() != 0) {
      delay(200); // poll periodically - no need to hammer the I2C bus every loop
    }
  } else {
    Serial.println("No RTC found - auto-starting now (no wall clock available to align to).");
  }
  doStart();
}

void loop() {
  // ---- check for serial commands ----
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.equalsIgnoreCase("start")) {
      doStart(); // same routine the minute-aligned post-boot auto-start uses
    }
    else if (cmd.equalsIgnoreCase("stop")) {
      running = false;
      analogWrite(pwmPin1, 0);
      analogWrite(pwmPin2, 0);
      analogWrite(pwmPinTEG, 0);
      Serial.println("STOPPED. All PWM outputs set to 0.");
    }
    else if (cmd.startsWith("set ")) {
      // NOTE: this is a manual override only. Sweeps ignore currentPWM
      // entirely (they use their own start/end/step defaults), and every
      // sweep forces the MOSFET straight back to PWM=0 once it finishes -
      // so a value set here while running will hold only until the next
      // (auto- or manually-triggered) sweep resets it back to 0.
      int newVal = cmd.substring(4).toInt();
      if (newVal >= 0 && newVal <= 255) {
        currentPWM = newVal;
        Serial.print("PWM value set to ");
        Serial.println(currentPWM);
        if (running) {
          analogWrite(pwmPin1, currentPWM);
          analogWrite(pwmPin2, currentPWM);
          analogWrite(pwmPinTEG, currentPWM);
          Serial.println("(applied immediately to pins 5, 12 & 8 - will be reset to 0 at the next sweep)");
        } else {
          Serial.println("(will apply to pins 5, 12 & 8 on next 'start', until the initial sweep resets it to 0)");
        }
      } else {
        Serial.println("Invalid value. Use 0-255.");
      }
    }
    else if (cmd.equalsIgnoreCase("sweep") || cmd.startsWith("sweep ")) {
      int startPWM = SWEEP_START_DEFAULT;
      int endPWM = SWEEP_END_DEFAULT;
      int step = SWEEP_STEP_DEFAULT;
      unsigned long dwellMs = SWEEP_DWELL_MS_DEFAULT;

      if (cmd.length() > 5) { // there's something after "sweep"
        int parsed = sscanf(cmd.c_str(), "sweep %d %d %d %lu", &startPWM, &endPWM, &step, &dwellMs);
        if (parsed != 4) {
          Serial.println("Could not parse 'sweep <start> <end> <step> <dwellMs>' - using defaults instead.");
          startPWM = SWEEP_START_DEFAULT;
          endPWM = SWEEP_END_DEFAULT;
          step = SWEEP_STEP_DEFAULT;
          dwellMs = SWEEP_DWELL_MS_DEFAULT;
        }
      }
      // Capture the current running state BEFORE runSweep() clears it, so
      // a manually-triggered sweep still restores whatever was active
      // beforehand (unlike the "start"-triggered initial sweep, which
      // always forces running=true afterward). This also resets the
      // 15-minute auto-sweep timer to count from this manual sweep instead.
      bool wasRunning = running;
      runSweep(startPWM, endPWM, step, dwellMs, wasRunning);
    }
    else {
      Serial.println("Unknown command. Use: start / stop / set <value> / sweep [start end step dwellMs]");
    }
  }

  // ---- take, print AND log a reading every RECURRING_INTERVAL_MS (1 min) ----
  // while running. (runSweep() temporarily sets running=false while it's
  // in control, so this block - and therefore the voltage log - goes quiet
  // during a sweep and picks back up once runSweep() restores the
  // resumeRunning state.)
  //
  // IMPORTANT: this block runs BEFORE the auto-sweep check below, on
  // purpose. Because sweep 1 (and every recurring reading after it) is
  // aligned to the RTC's whole-minute marks, and 15 minutes is itself a
  // whole number of those 1-minute steps, sweep 2 (and every 15-minute
  // sweep after it) always lands on a minute where a recurring reading is
  // ALSO due - e.g. both come due at 15:00:00. When that happens, we want
  // the recurring reading taken FIRST (at the PWM=0 idle state) and only
  // THEN the sweep started - not the other way around. Since both checks
  // re-test `running` fresh each pass, and this one doesn't change
  // `running` itself, this ordering is enough to guarantee that without
  // any extra bookkeeping. Taking that reading (I2C reads + 8x MAX6675 +
  // Serial print + SD write) isn't instant - in practice it costs on the
  // order of ~250ms - so the sweep that follows starts a fraction of a
  // second after the clean minute mark, not at exactly :00.000.
  if (running && millis() - lastRead >= RECURRING_INTERVAL_MS) {
    lastRead = millis();
    takeAndLogReading();
  }

  // ---- auto-sweep every 15 minutes, timed START-to-START, while running ----
  // Only armed while `running` is true, so 'stop' also halts the schedule;
  // the very first sweep (triggered by "start", above) already stamped
  // lastSweepStartMillis, so this simply keeps repeating from there. This
  // check runs AFTER the recurring-read block above so that a reading due
  // at the same moment as a sweep gets logged first (see the comment there).
  // A full 0-255 sweep at 50ms/step takes about 40 s in practice (12.8 s of
  // dwell plus roughly 155 ms per step in total for the readings and the
  // logging), which is still well under a minute, so it always finishes
  // before the NEXT 1-minute recurring reading would come due and no
  // recurring reading is ever skipped, even on a minute where a sweep also
  // fires.
  if (running && millis() - lastSweepStartMillis >= AUTO_SWEEP_INTERVAL_MS) {
    Serial.println("AUTO-SWEEP: 15 minutes since the last sweep started - running scheduled sweep...");
    // resumeRunning=true: an auto-triggered sweep only ever fires while the
    // system is already running, so it must leave it running afterward too.
    runSweep(SWEEP_START_DEFAULT, SWEEP_END_DEFAULT, SWEEP_STEP_DEFAULT, SWEEP_DWELL_MS_DEFAULT, true);
  }
}

// Takes one PV1+PV2+TEG+BPW+8xTC reading and prints/logs it to the voltage
// log - the same body the recurring block used to run inline. Pulled out
// into its own function so runSweep() can also call it immediately after a
// sweep finishes, instead of waiting for the next 1-minute tick.
void takeAndLogReading() {
  float busVoltage1 = ina219_1.getBusVoltage_V();
  float current1_mA = ina219_1.getCurrent_mA();
  float power1_mW = busVoltage1 * current1_mA;

  float busVoltage2 = ina219_2.getBusVoltage_V();
  float current2_mA = ina219_2.getCurrent_mA();
  float power2_mW = busVoltage2 * current2_mA;

  // ---- TEG channel via ADS1115 ----
  float busVoltageTEG = ads_teg.computeVolts(ads_teg.readADC_SingleEnded(0)); // A0 = string voltage
  float shuntVoltage   = ads_teg.computeVolts(ads_teg.readADC_SingleEnded(1)); // A1 = shunt voltage directly
  float currentTEG_A = shuntVoltage / SHUNT_RESISTANCE_TEG;
  if (currentTEG_A < 0) currentTEG_A = 0; // a reversed (negative) TEG current is recorded as zero
  float currentTEG_mA = currentTEG_A * 1000.0;
  float powerTEG_mW = busVoltageTEG * currentTEG_mA;

  // ---- BPW photodiode channel via ADS1115 (A2) ----
  float bpwVoltage = ads_teg.computeVolts(ads_teg.readADC_SingleEnded(2));
  if (bpwVoltage < 0) bpwVoltage = 0; // a negative reading (offset/noise) is recorded as zero

  // ---- 8x thermocouples (MAX6675, software SPI) ----
  // A reading of "nan" means that channel's thermocouple is open/disconnected.
  String tcPart = "";
  for (int i = 0; i < NUM_THERMOCOUPLES; i++) {
    float tempC = thermocouples[i].readCelsius();
    tcPart += "," + String(tempC, 2);
  }

  String ts = getTimestampString();

  String row = ts + "," + String(currentPWM) + "," +
               String(busVoltage1, 3) + "," + String(current1_mA, 2) + "," + String(power1_mW, 2) + "," +
               String(busVoltage2, 3) + "," + String(current2_mA, 2) + "," + String(power2_mW, 2) + "," +
               String(busVoltageTEG, 3) + "," + String(currentTEG_mA, 2) + "," + String(powerTEG_mW, 2) + "," +
               String(bpwVoltage, 3) + tcPart;

  Serial.println(row);
  logLine(voltLogFileName.c_str(), VOLT_HEADER, row);
}

// Sweeps the PWM held on pins 5, 12 & 8 together from startPWM to endPWM
// in increments of step, dwelling dwellMs at each step before logging one
// row of PV panel 1 (INA219 #1) + PV panel 2 (INA219 #2) + TEG (ADS1115 A0
// voltage, A1 shunt -> current) + BPW readings - to Serial AND to the sweep
// CSV. Recurring voltage logging is suppressed for the duration (by
// temporarily clearing `running`). Unlike before, there's no "previous PWM"
// restored afterward - the MOSFET is ALWAYS held at PWM=0 once the sweep
// ends, whether or not recurring readings resume; the sweep loop itself is
// the only time PWM ever goes non-zero. Whether recurring readings resume
// at all is NOT auto-detected here - it's decided by the caller via
// resumeRunning, because the very first ("start"-triggered) sweep must
// always leave the system running afterward even though `running` was
// false at the moment it was called, while a manual "sweep" command should
// restore whatever was active before it, and an auto-scheduled sweep
// should simply keep the system running.
// Also stamps lastSweepStartMillis at the very top, before anything else,
// so the 15-minute auto-sweep schedule is always timed from this sweep's
// actual START, no matter what triggered it, and bumps sweepCount so a
// "Sweep N" marker row can be written ahead of this sweep's own data rows.
void runSweep(int startPWM, int endPWM, int step, unsigned long dwellMs, bool resumeRunning) {
  lastSweepStartMillis = millis(); // mark this sweep's start for the 15-min start-to-start schedule
  sweepCount++;

  startPWM = constrain(startPWM, 0, 255);
  endPWM = constrain(endPWM, 0, 255);
  if (step == 0) step = 1;
  if (endPWM < startPWM && step > 0) step = -step;
  if (endPWM > startPWM && step < 0) step = -step;

  running = false; // stops the periodic voltage/TC log block during the sweep

  const char* sweepHeader = "Timestamp,PWM,V1_PV1(V),I1_PV1(mA),P1_PV1(mW),V2_PV2(V),I2_PV2(mA),P2_PV2(mW),V_TEG(V),I_TEG(mA),P_TEG(mW),V_BPW(V)";

  // Reserve a marker row ahead of this sweep's own data rows - the sweep
  // log accumulates every sweep's rows across the whole session, so
  // without a marker there'd be no way to tell where one sweep's data ends
  // and the next one's begins.
  String sweepMarker = "Sweep " + String(sweepCount);
  Serial.println(sweepMarker);
  logLine(sweepLogFileName.c_str(), sweepHeader, sweepMarker);

  Serial.print("SWEEP START: ");
  Serial.print(startPWM);
  Serial.print(" -> ");
  Serial.print(endPWM);
  Serial.print(" step ");
  Serial.print(step);
  Serial.print(", dwell ");
  Serial.print(dwellMs);
  Serial.println("ms per step");
  Serial.println(sweepHeader);

  for (int pwmVal = startPWM; (step > 0) ? (pwmVal <= endPWM) : (pwmVal >= endPWM); pwmVal += step) {
    analogWrite(pwmPin1, pwmVal);
    analogWrite(pwmPin2, pwmVal);
    analogWrite(pwmPinTEG, pwmVal);

    delay(dwellMs); // let the MOSFET/load settle at this duty cycle before reading

    // PV panel 1, PV panel 2, and the TEG, taken back-to-back so they're as
    // close to simultaneous as a single microcontroller loop allows.
    float busVoltage1 = ina219_1.getBusVoltage_V();
    float current1_mA = ina219_1.getCurrent_mA();
    float power1_mW = busVoltage1 * current1_mA;

    float busVoltage2 = ina219_2.getBusVoltage_V();
    float current2_mA = ina219_2.getCurrent_mA();
    float power2_mW = busVoltage2 * current2_mA;

    float busVoltageTEG = ads_teg.computeVolts(ads_teg.readADC_SingleEnded(0));
    float shuntVoltageTEG = ads_teg.computeVolts(ads_teg.readADC_SingleEnded(1));
    float currentTEG_A = shuntVoltageTEG / SHUNT_RESISTANCE_TEG;
    if (currentTEG_A < 0) currentTEG_A = 0; // a reversed (negative) TEG current is recorded as zero
    float currentTEG_mA = currentTEG_A * 1000.0;
    float powerTEG_mW = busVoltageTEG * currentTEG_mA;

    // ---- BPW photodiode channel via ADS1115 (A2) ----
    float bpwVoltage = ads_teg.computeVolts(ads_teg.readADC_SingleEnded(2));
    if (bpwVoltage < 0) bpwVoltage = 0; // a negative reading (offset/noise) is recorded as zero

    String ts = getTimestampString();

    String row = ts + "," + String(pwmVal) + "," +
                 String(busVoltage1, 3) + "," + String(current1_mA, 2) + "," + String(power1_mW, 2) + "," +
                 String(busVoltage2, 3) + "," + String(current2_mA, 2) + "," + String(power2_mW, 2) + "," +
                 String(busVoltageTEG, 3) + "," + String(currentTEG_mA, 2) + "," + String(powerTEG_mW, 2) + "," +
                 String(bpwVoltage, 3);

    Serial.println(row);
    logLine(sweepLogFileName.c_str(), sweepHeader, row);
  }

  Serial.println("SWEEP COMPLETE");

  // The MOSFET always lands back at PWM=0 once a sweep ends - there's no
  // "previous PWM" to restore, since recurring readings never hold
  // anything else. Only `running` (whether recurring readings are active
  // at all) is decided by the caller via resumeRunning (see the big
  // comment above this function for why that's a parameter).
  currentPWM = 0;
  analogWrite(pwmPin1, 0);
  analogWrite(pwmPin2, 0);
  analogWrite(pwmPinTEG, 0);
  running = resumeRunning;
  if (running) {
    Serial.println("Recurring readings resumed. MOSFET held at PWM = 0 between sweeps.");
    Serial.println(VOLT_HEADER);

    // Re-align to the wall clock right here, every single time a sweep
    // ends: wait until the RTC's seconds reads exactly 0 again before
    // taking the next recurring reading. This is what keeps recurring
    // readings landing on clean minute marks (:01:00, :02:00, ... :16:00,
    // ...) FOREVER, instead of drifting later by roughly one sweep's
    // duration (~40 s) every single time a sweep runs. As a side benefit,
    // this wait is also comfortably longer than the INA219/ADS1115 input
    // filters' settling time (~940ms and ~100ms time constants), so unlike
    // an instant reading, this one is always fully settled at PWM=0 by the
    // time it's taken.
    //
    // If the RTC isn't available, there's no wall-clock second to align
    // to, so this reading is just taken right away instead.
    if (rtcReady) {
      Serial.println("Waiting for the next full minute (RTC seconds = 00) before the next recurring reading...");
      while (rtc.now().second() != 0) {
        delay(200); // poll periodically - no need to hammer the I2C bus every loop
      }
    }
    takeAndLogReading();
    lastRead = millis(); // recurring readings from here on are timed relative to this instant
  } else {
    Serial.println("Recurring readings remain stopped. Use 'start' to begin them.");
  }
}

// Returns "YYYY-MM-DD HH:MM:SS" from the DS3231 if it's available, or a
// "T+<millis>ms" fallback (time since boot) if the RTC wasn't found.
String getTimestampString() {
  if (!rtcReady) {
    return "T+" + String(millis()) + "ms";
  }
  DateTime now = rtc.now();
  char buf[20];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02d %02d:%02d:%02d",
           now.year(), now.month(), now.day(),
           now.hour(), now.minute(), now.second());
  return String(buf);
}

// Appends one CSV row to filename on the SD card, writing `header` first
// if the file doesn't already exist. Does nothing (silently) if the SD
// card failed to initialize in setup().
void logLine(const char* filename, const char* header, const String& row) {
  if (!sdReady) return;

  bool isNewFile = !SD.exists(filename);
  File dataFile = SD.open(filename, FILE_WRITE); // FILE_WRITE appends, doesn't overwrite
  if (dataFile) {
    if (isNewFile) {
      dataFile.println(header);
    }
    dataFile.println(row);
    dataFile.close();
  } else {
    Serial.print("WARNING: could not open ");
    Serial.print(filename);
    Serial.println(" on SD card - this row was not logged to file.");
  }
}
