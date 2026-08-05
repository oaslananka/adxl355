# ADXL355 Hardware-in-the-Loop Testing

This guide defines the public wiring assumptions, runner setup, execution
procedure, and diagnostic evidence for the opt-in ADXL355 hardware-in-the-loop
(HIL) workflow. HIL is deliberately separate from the default unit-test suite and
runs only through manual workflow dispatch on a dedicated self-hosted runner.

## Safety and supported hardware assumptions

The ADXL355 supply range is **2.25 V to 3.6 V**. `VDDIO` must follow the voltage
limits of the connected host interface; for a raw ADXL355 design, use the
specified 2.5 V to 3.6 V I/O range. Never apply 5 V directly to a raw sensor pin.
A breakout board may include a regulator or level shifters, but those features
must be confirmed from that board's schematic before wiring.

The documented fixture assumes:

- one genuine ADXL355 or a breakout exposing the complete digital interface;
- a Linux host with either `/dev/spidevB.C` or `/dev/i2c-B`;
- short point-to-point wiring and a shared ground;
- no other process accessing the selected bus while the test runs;
- a stable, low-noise supply suitable for the sensor and the host's logic level;
- the sensor mounted so unexpected motion does not dominate the continuous-read
  check.

Power off both boards before changing wiring or the MISO/ASEL address strap.

## SPI fixture

The runner uses 4-wire SPI, **SPI Mode 0** (`CPOL=0`, `CPHA=0`), eight bits per
word, and a clock from **100 kHz to 10 MHz**. The default workflow value is 1 MHz.

| ADXL355 signal | Linux host signal | Notes |
|---|---|---|
| `VDD` | regulated sensor supply | 2.25 V to 3.6 V |
| `VDDIO` | host logic supply | Match host logic voltage; do not assume 5 V tolerance |
| `GND` and exposed pad | host ground | Common ground is mandatory |
| `SCLK/VSSIO` | SPI clock | Mode 0 clock |
| `MOSI/SDA` | MOSI | Host to sensor |
| `MISO/ASEL` | MISO | Sensor to host in SPI mode |
| `CS/SCL` | chip select | Active low; use the selected `/dev/spidevB.C` node |
| `DRDY` or `INT1/INT2` | optional GPIO/logic analyzer | The runner polls `STATUS.DATA_RDY`; no GPIO input is required |

Start at 100 kHz or 1 MHz when diagnosing a new fixture. Increase the clock only
after identity, reset, and continuous-read checks are stable.

![Verified Raspberry Pi 5 SPI wiring: physical pin 1 to 3.3 V, pin 6 to GND,
pin 23 GPIO11 to SCLK, pin 19 GPIO10 to MOSI, pin 21 GPIO9 to MISO, pin 24
GPIO8/CE0 to CS, and optional pin 11 GPIO17 to DRDY.](media/raspberry-pi-5-spi-adxl355.svg)

The diagram is an original MIT-licensed repository asset. Its complete text
alternative is embedded in the SVG and the same mapping remains available in the
table above. The optional DRDY line is dashed because the maintained runner polls
`STATUS.DATA_RDY` over SPI.

## I2C fixture

For I2C, tie **`SCLK/VSSIO` to ground** and use pull-ups from `MOSI/SDA` and
`CS/SCL` to `VDDIO`. The `MISO/ASEL` strap selects the address:

| `MISO/ASEL` strap | 7-bit address |
|---|---|
| ground | `0x1D` |
| `VDDIO` | `0x53` |

| ADXL355 signal | Linux host signal | Notes |
|---|---|---|
| `VDD` | regulated sensor supply | 2.25 V to 3.6 V |
| `VDDIO` | pull-up/host logic supply | Use one compatible logic voltage |
| `GND` and exposed pad | host ground | Common ground is mandatory |
| `SCLK/VSSIO` | ground | Required for I2C mode |
| `MOSI/SDA` | SDA | Pull up to `VDDIO` |
| `CS/SCL` | SCL | Pull up to `VDDIO` |
| `MISO/ASEL` | ground or `VDDIO` | Selects `0x1D` or `0x53` |
| `DRDY` | GPIO17 / physical pin 11 | Optional dedicated active-high rising-edge input for the bounded libgpiod example |

![Verified Raspberry Pi 5 I2C wiring: physical pin 1 to 3.3 V, pin 6 to GND,
pin 3 GPIO2/SDA1 to MOSI/SDA, pin 5 GPIO3/SCL1 to CS/SCL, pin 9 GND to
SCLK/VSSIO for I2C mode, pin 14 GND to MISO/ASEL for address 0x1D, and optional
pin 11 GPIO17 to DRDY.](media/raspberry-pi-5-i2c-adxl355.svg)

The diagram is an original MIT-licensed repository asset matched to the physical
fixture used in workflow run
[30734635341](https://github.com/oaslananka/adxl355/actions/runs/30734635341).
Its complete text alternative is embedded in the SVG and the same mapping remains
available in the table above. Raspberry Pi SDA/SCL provide host-side pull-ups;
custom hosts must provide pull-ups to the selected compatible logic rail.

Only address `0x1D` is physically verified. Testing `0x53` requires powering down,
moving `MISO/ASEL` from ground to `VDDIO`, and repeating the full evidence flow.

The workflow accepts declared bus rates of 100 kHz, 400 kHz, 1 MHz, or 3.4 MHz.
Linux adapters do not provide a portable API for changing the controller clock,
so configure the bus speed in the host platform and pass the matching declared
value to the workflow. Test both `0x1D` and `0x53` when the product fixture
supports changing the strap.

## Dedicated DRDY GPIO fixture

The dedicated `DRDY` output is separate from routing the `DATA_RDY` condition to
`INT1` or `INT2`. Rev.D defines dedicated DRDY as active high; `RANGE.INT_POL`
controls only INT1/INT2. `POWER_CTL.DRDY_OFF=1` forces dedicated DRDY low. The
maintained C/Python configuration API supports internal synchronization only,
because external clock/synchronization modes multiplex DRDY or INT2 differently.

The optional Raspberry Pi fixture maps ADXL355 `DRDY` to GPIO17 (physical pin
11). Request it as a normal input with rising-edge detection, disabled bias, and
a monotonic event clock. Do not set `active_low`, do not poll the line in a busy
loop, and do not use INT1/INT2 polarity settings to describe the dedicated pin.
Power down before adding or moving the wire.

The repository reference command is finite and Linux-only:

```bash
python -m pip install -e 'python[i2c,gpio]'
cd python
PYTHONPATH=src python -m examples.linux_drdy \
  --transport i2c --bus 1 --address 0x1D \
  --gpio-chip /dev/gpiochip0 --gpio-line 17 \
  --samples 32 --timeout-s 5 --max-missed-events 0
```

For a reproducible fixture run, record the exact commit, Python and libgpiod
versions, bus settings, GPIO chip/offset, requested sample count, actual sample
count, first/last kernel timestamps, line-sequence gaps, FIFO overrun count, and
independent post-run readback of standby, ±2 g, default ODR, `INT_MAP`, and
`DRDY_OFF`. Use a separate `/tmp` checkout and an outer process timeout. Do not
record the host name, private address, environment, credentials, or raw device
paths beyond the public fixture mapping.

Unit tests prove the bounded event/lifecycle contract with fake GPIO requests;
they do not prove the wire.

### Recorded dedicated DRDY result

A bounded physical run succeeded on **2026-08-02** against exact implementation
commit `002173d0c8dae8b15261b6d00cf011011cf8db7c` on the dedicated Raspberry Pi 5
I2C fixture:

- runtime: Linux ARM64, Python `3.13.5`, libgpiod Python binding `2.2.0`, and
  `smbus2 0.4.3`;
- sensor bus: I2C bus 1 at address `0x1D`; event input: `/dev/gpiochip0` line 17;
- bounds: 32 requested samples, a 5-second acquisition deadline, zero allowed
  missed events, and a 20-second outer process timeout;
- result: 32 samples, 32 unique raw XYZ tuples, GPIO line sequence 1 through 32,
  zero missed events, and zero FIFO overruns;
- timing: 250,573,771 ns total duration, event intervals from 8,028,153 ns to
  8,034,245 ns, and maximum event-to-capture latency of 1,630,712 ns; and
- independent post-run register readback: `POWER_CTL=0x01`, `RANGE=0x81`,
  `FILTER=0x00`, `INT_MAP=0x00`, and `SYNC=0x00`, confirming standby, enabled
  dedicated DRDY, ±2 g, default ODR, no DATA_RDY mapping to INT1/INT2, and
  internal synchronization. GPIO17 was released and returned to an unclaimed
  input state.

The command ran as the non-root fixture account from a separate `/tmp` checkout
and exited normally. No host name, private address, environment dump, credential,
or raw report was committed. This evidence is intentionally scoped to I2C plus
the dedicated active-high DRDY output on GPIO17. It does **not** prove SPI DRDY,
INT1/INT2-routed DATA_RDY, external synchronization, or other GPIO offsets.

## What the runner verifies

`scripts/hil_runner.py` executes one bounded sequence:

1. validate the selected bus configuration;
2. read `DEVID_AD`, `DEVID_MST`, `PARTID`, and the device revision (`REVID`);
3. run the public `probe()` path;
4. issue a software reset and confirm the identity and default ±2 g range;
5. configure ±4 g, 125 Hz ODR, and measurement mode, then read back the settings;
6. read a coherent temperature sample and require a finite value inside the
   ADXL355 operating range;
7. wait for `DATA_READY` and capture multiple raw XYZ samples, rejecting invalid
   signed 20-bit values, a frozen sample stream, or acceleration outside the
   configured range;
8. return the device to standby, ±2 g, and the default ODR;
9. close the Linux adapter and write a sanitized JSON report.

The report contains the tested commit, public fixture identifier, operating
system/kernel/architecture, Python version, bus settings, identity values, device
revision, step durations, temperature, bounded sample summaries, and diagnostic
hints. It never copies the process environment, host name, credentials, or raw
secret values. Strings resembling tokens, passwords, secrets, or API keys are
redacted.

## Electrostatic self-test response

The maintained C and Python drivers implement the Rev.D response sequence as a
bounded diagnostic measurement:

1. save `SELF_TEST`, `RANGE`, `FILTER`, `POWER_CTL`, and the cached range;
2. configure ±2 g, 125 Hz, and measurement mode;
3. enable ST1 only and collect the baseline mean;
4. enable ST1+ST2 and collect the stimulated mean;
5. report signed and absolute per-axis delta values;
6. restore every saved register and cached range on success or failure.

Rev.D specifies self-test output-change limits in g:

| Axis | Minimum | Typical | Maximum |
|---|---:|---:|---:|
| X | 0.1 | 0.3 | 0.6 |
| Y | 0.1 | 0.3 | 0.6 |
| Z | 0.5 | 1.5 | 3.0 |

Default calls still report measurements without applying pass/fail policy. A
caller may explicitly supply the Rev.D windows or a narrower, documented fixture
policy. A fixture-specific policy must not be presented as an Analog Devices
production limit. Timeout, transport, threshold, and restoration failures remain
distinct. Physical validation must also compare every saved register before and
after the run.

## Local opt-in execution

Install only the selected adapter and run the command explicitly. These commands
are not part of normal `pytest` discovery.

```bash
python3 -m venv .venv-hil
. .venv-hil/bin/activate
export PIP_CONFIG_FILE=/dev/null
export PIP_INDEX_URL=https://pypi.org/simple
export PIP_EXTRA_INDEX_URL=
python -m pip install --disable-pip-version-check \
  --require-hashes --no-deps --only-binary=:all: \
  -r requirements/python/hil-build.txt
python -m pip install --disable-pip-version-check \
  --no-build-isolation --no-deps -e ./python

# SPI example: /dev/spidev0.0, Mode 0, 1 MHz
python -m pip install --disable-pip-version-check \
  --require-hashes --no-build-isolation --no-deps \
  -r requirements/python/hil-spi.txt
python scripts/hil_runner.py \
  --transport spi \
  --spi-bus 0 \
  --spi-device 0 \
  --spi-speed-hz 1000000 \
  --samples 32 \
  --report artifacts/hil-report.json

# I2C example: /dev/i2c-1, address 0x1D
python -m pip install --disable-pip-version-check \
  --require-hashes --no-deps --only-binary=:all: \
  -r requirements/python/hil-i2c.txt
python scripts/hil_runner.py \
  --transport i2c \
  --i2c-bus 1 \
  --i2c-address 0x1D \
  --i2c-bus-hz 100000 \
  --samples 32 \
  --report artifacts/hil-report.json
```

A missing device node or failed transfer returns a nonzero status and still writes
an actionable JSON report when the runner reaches the CLI. Do not use production
credentials in command-line values or the public `runner_id` field.

## Self-hosted GitHub runner setup

Use a dedicated Linux machine or isolated lab account:

1. install GitHub Actions Runner **2.327.1 or later** using the
   repository/organization setup instructions; the pinned checkout and artifact
   actions execute on the **Node.js 24** action runtime;
2. add the labels `self-hosted`, `linux`, and `adxl355-hil`;
3. add the runner account to the group permitted to access the selected `spidev`
   or `i2c-dev` node, preferably through a narrow udev rule;
4. install a supported Python 3.10 or later with the `venv` module, a C compiler
   needed by `spidev`, and the Linux SPI/I2C kernel modules; the workflow uses the
   runner's provisioned `python3` inside a job-local virtual environment rather
   than downloading a runtime with `actions/setup-python`;
5. disable unrelated services that might claim the bus;
6. keep registry credentials and other secrets off this runner; the HIL workflow
   requests only read access to repository contents and persists no GitHub token;
7. connect only one known fixture and give it a non-secret public identifier.

The workflow `.github/workflows/hil.yml` is manual-only. Select **Actions →
Hardware-in-the-Loop → Run workflow**, choose SPI or I2C, enter the bounded bus
settings, and download the 30-day `artifacts/` evidence bundle after completion.
The bundle includes `runner-context.txt` and `hil-report.json`.

### Runner scope and threat model

The maintained fixture is repository-scoped to `oaslananka/adxl355`, uses the
public runner name `adxl355-hil`, and exposes only the labels `self-hosted`,
`Linux`, `ARM64`, and `adxl355-hil`. Only the manual, `main`-restricted HIL
workflow may target that label. Pull-request, fork, and general CI workflows must
remain on GitHub-hosted runners and must never receive HIL host credentials.

The service runs as the unprivileged `pi` account through
`actions.runner.oaslananka-adxl355.adxl355-hil.service`. Bus access comes from the
narrow `spi` and `i2c` groups; the runner service is not run as root. Registry,
production, Doppler, cloud, and package-publishing credentials are prohibited on
this host.

### Monthly health and update check

Run bounded checks without printing the process environment or credential files:

```bash
systemctl is-enabled actions.runner.oaslananka-adxl355.adxl355-hil.service
systemctl is-active actions.runner.oaslananka-adxl355.adxl355-hil.service
cd ~/actions-runner && ./bin/Runner.Listener --version
python3 --version
gcc --version | head -1
id
test -r /dev/spidev0.0 && test -w /dev/spidev0.0
find /dev -maxdepth 1 -name 'i2c-*' -printf '%f\n'
df -h /home
stat -c '%a %U:%G %n' ~/.ssh/authorized_keys \
  ~/actions-runner/.credentials ~/actions-runner/.credentials_rsaparams \
  ~/actions-runner/.runner ~/actions-runner/.env ~/actions-runner/.path
```

Compare the installed runner with the latest official `actions/runner` release.
Apply Debian security updates during a planned window, restart the service, and
confirm it returns to `online`/`idle`. Credential-bearing runner files and
runner-captured environment/path files must be owned by the runner account and
mode `0600`. Do not display their contents in logs or issues.

After maintenance, dispatch a bounded SPI or I2C HIL smoke run, verify the JSON
report, and confirm the fixture is restored to standby, ±2 g, and the default
ODR. A maintenance smoke result does not replace release-candidate evidence.

### Quarterly access review

Record the completed review in the tracking issue or private operations inventory,
not as a raw repository audit file. Verify all of the following:

- the GitHub runner remains repository-scoped, online, and labeled only for HIL;
- no non-HIL workflow references `self-hosted` or `adxl355-hil`;
- Tailscale device ownership, ACL/tag scope, and SSH access still match the named
  maintainers and operations hosts;
- `authorized_keys` fingerprints and local `sudo`, `spi`, and `i2c` group
  membership contain only expected principals;
- GitHub Apps/OAuth grants and repository runner registrations are still needed;
- no `.npmrc`, `.pypirc`, Cargo credential file, Docker registry config, Doppler
  project config, production secret, or long-lived registry token exists;
- the physical fixture identifier is non-secret and still maps to one known
  sensor/wiring configuration.

Unexpected access is removed before another HIL or release run. Rotate or revoke
credentials through their source system; never paste replacement values into the
repository, an issue, or a workflow input.

### Workspace, log, and evidence cleanup

GitHub HIL artifacts are retained for 30 days. Preserve artifacts referenced by
an active release candidate until the release record is complete. On the runner,
clean only inactive `_work` job directories, temporary virtual environments, and
old diagnostic logs after confirming no job is running. Keep enough recent
`_diag` and systemd journal entries to diagnose the last failure, but do not use
the runner as a release artifact archive. Disk cleanup must not remove source
inputs, the runner installation, current release evidence, or the configured
service.

### Rebuild, revocation, and retirement

A rebuild records only non-secret configuration: repository URL, runner name,
labels, service account, required packages, and bus permissions. Install a clean
OS/runner release and register it with a new short-lived GitHub registration
token. Do not copy `.credentials`, `.credentials_rsaparams`, registry files, or
SSH private keys from the previous host.

For retirement:

1. stop and uninstall the systemd runner service;
2. remove the runner registration from the repository and verify it no longer
   appears online or offline in GitHub settings;
3. delete local runner credential files and revoke the device's Tailscale/SSH
   access;
4. disconnect or power down the fixture;
5. confirm the old runner cannot accept a job, then remove the machine from the
   private operations inventory.

If an update fails, stop the new service, restore the previously verified runner
installation only when its credentials have not been revoked, and repeat the
service/connectivity/HIL health checks.

## Troubleshooting

### Device node missing

Confirm the kernel module, device-tree overlay, controller enablement, and runner
permissions. Check only the selected `/dev/spidevB.C` or `/dev/i2c-B` node; do not
publish a full device listing or environment dump.

### Identity mismatch

Power down and verify supply voltage, common ground, chip select/address strap,
and point-to-point wiring. For SPI, verify Mode 0 and inspect the first four
identity reads with a logic analyzer. For I2C, scan the isolated bus for `0x1D` or
`0x53`, then stop the scanner before running HIL.

### SPI transfer or frozen samples

Lower the clock toward 100 kHz, shorten wires, verify chip-select remains asserted
for command plus payload, and confirm no second process opens the device. A stream
with one repeated sample fails intentionally because it cannot demonstrate
continuous conversion.

### I2C NACK or intermittent data

Verify `SCLK/VSSIO` is grounded, the pull-ups connect to `VDDIO`, the selected
address matches `MISO/ASEL`, and the host bus rate matches the declared workflow
value. Avoid multi-device layouts that violate the ADXL355 point-to-point timing
assumptions.

### Temperature outside range

Confirm the device is an ADXL355, check supply stability and register framing, and
allow the board to reach thermal equilibrium. The runner rejects non-finite values
and temperatures outside the sensor operating range.

### Permission denied

Grant the dedicated runner account narrow group/udev access to the selected node.
Do not solve persistent permission problems by running the entire GitHub runner as
root.

## Current recorded evidence

A manual SPI integration run succeeded on Raspberry Pi 5 against commit
`4505385518dc62522888560700dc12cb2c8d0467`:

- workflow run: [30725059679](https://github.com/oaslananka/adxl355/actions/runs/30725059679);
- transport and device: SPI Mode 0 on `/dev/spidev0.0` at 1 MHz;
- identity: `DEVID_AD=0xAD`, `DEVID_MST=0x1D`, `PARTID=0xED`;
- revision: `0x01`;
- samples: 32 captured and 32 unique;
- restore state: standby, ±2 g, default ODR.

This result proves the integrated SPI path and runner setup. A separate I2C HIL
integration run also succeeded on `main` commit
`43629a5d5f0eb9ff815cdbdd26288e904ba3a573`:

- workflow run: [30734635341](https://github.com/oaslananka/adxl355/actions/runs/30734635341);
- transport and device: I2C bus 1, address `0x1D`, declared 100 kHz;
- identity: `DEVID_AD=0xAD`, `DEVID_MST=0x1D`, `PARTID=0xED`;
- revision: `0x01`;
- temperature: `28.6464 °C`;
- samples: 32 captured and 32 unique;
- artifact: `adxl355-hil-i2c-30734635341` with 30-day retention.

These runs remain useful feature evidence. The final paired release evidence for
[`v0.1.0-alpha.3`](https://github.com/oaslananka/adxl355/releases/tag/v0.1.0-alpha.3)
was produced on exact commit `71de69b8727a9f8eef254de586d9bce7bc8fa8ac`:
SPI run `30736413982` and I2C run `30736668298`. Both captured 32/32 unique
samples, verified identity `0xAD/0x1D/0xED` and revision `0x01`, measured
29.1989 °C, and passed standby/±2 g/default-ODR restoration. The release stores
permanent sanitized reports as `hil-spi-30736413982.json` and
`hil-i2c-30736668298.json`. The I2C release fixture was strapped to address
`0x1D`; address `0x53` was not physically validated for this prerelease.

### Go Linux SPI bounded example

The maintained Go `adxl355/linuxio` spidev adapter and bounded example were
physically verified on the Raspberry Pi 5 SPI fixture using code commit
`08273bff4611a33f1b88dae6a08c92d5199eab28`. The ARM64 binary was built only from
a `git archive` of that commit; its SHA-256 was
`a74fd41821d3decc8a4e67d31411659487af83106b697b124975255f5749f2de`, and the
same hash was checked on the fixture before execution.

The public-safe invocation was:

```bash
go run ./examples/linux_spi \
  --bus 0 --device 0 --speed-hz 1000000 \
  --samples 32 --timeout 15s
```

The run established:

- identity `0xAD/0x1D/0xED`, revision `0x01`;
- temperature `28.0939 °C` after entering measurement mode and a bounded settle;
- 32 nonzero XYZ samples, including 29 unique tuples; and
- independent post-run `POWER_CTL=0x01`, proving standby restoration after the
  bounded command closed its owned descriptor.

An earlier pre-fix run exposed a real lifecycle defect: reading temperature before
measurement returned a zero raw value and an implausible `233.2873 °C`, while the
first acceleration frame was empty. The final implementation moves measurement
before temperature, waits through a bounded settle interval, and preserves this
ordering in a regression test whose mock returns zero temperature in standby.
That rejected run is not accepted as evidence.

This Go result is feature-specific SPI evidence. It is not a GitHub Actions HIL
artifact and does not satisfy the separate final release-candidate requirement.

### Go Linux I2C bounded example

The maintained Go `adxl355/linuxio` i2c-dev adapter and bounded example were
physically verified against exact `main` commit
`43629a5d5f0eb9ff815cdbdd26288e904ba3a573`. The ARM64 binary was built only from
a `git archive` of that commit; its SHA-256 was
`1c97921239baea9994942a4a77fbbd2b2048ba9f84e81f452d929bb7715c367c`, and the
same hash was checked on the fixture before execution.

The public-safe invocation was:

```bash
go run ./examples/linux_i2c \
  --bus 1 --address 0x1D --bus-hz 100000 \
  --samples 32 --timeout 10s
```

The run established:

- identity `0xAD/0x1D/0xED`, revision `0x01`;
- temperature `28.4254 °C` after entering measurement mode and a bounded settle;
- 32 nonzero XYZ samples with 32 unique tuples; and
- independent post-run `POWER_CTL=0x01`, proving standby restoration after the
  bounded command closed its owned descriptor.

This is feature-specific evidence for the physically tested `0x1D` strap. It does
not claim the alternate `0x53` strap or replace the final paired SPI/I2C release
artifacts.

A separate self-test response validation used the exact C/Python implementation
from commit `12d6206393223439e14b8e36b97e567751e8f8bb` on the same Raspberry Pi 5
SPI fixture at 1 MHz. Two independent 64-sample runs, each with eight discarded
settle samples, measured absolute response values:

| Run | X (g) | Y (g) | Z (g) |
|---|---:|---:|---:|
| 1 | 0.34236 | 0.33908 | 1.41865 |
| 2 | 0.34256 | 0.33893 | 1.41860 |

A third 64-sample run applied the Rev.D X/Y `0.10–0.60 g` and Z `0.50–3.00 g`
windows and passed with `0.34241/0.33896/1.41859 g`. Before every call the fixture
was configured to ±4 g, 250 Hz, and measurement mode. Each call restored the exact
pre-call `SELF_TEST`, `RANGE`, `FILTER`, and `POWER_CTL` bytes. A defensive final
restore also returned the original standby, ±2 g, default-filter state exactly.
The raw temporary JSON report is not stored in the repository. This evidence
validates the self-test feature on SPI; it does not replace final SPI/I2C
release-candidate HIL evidence.

## Node.js Linux adapter physical validation

Physical Node adapter evidence must use a clean package build from one exact
commit and a supported Node version. The examples are bounded and must run as the
non-root HIL runner account.

1. Build the Node package, explicitly rebuild the two exact optional native
   modules, and record Node/npm versions plus the tested commit.
2. On I2C, use bus 1, the physically strapped `0x1D` address, and the externally
   configured 100 kHz rate. Capture identity, temperature, finite sample count,
   uniqueness, and an independent post-run standby readback.
3. On SPI, use `/dev/spidev0.0`, Mode 0, and 1 MHz. Confirm command and payload
   stay in one chip-select transaction through the adapter unit contract, then
   record the same physical measurements and standby readback.
4. Enter measurement mode before temperature or acceleration reads and wait
   through the maintained bounded 20 ms settle interval.
5. Verify the example exits within its timeout, closes the native descriptor on
   both success and failure, and publishes no hostname, private address, or raw
   environment data.
6. Keep SPI and I2C evidence tied to the same implementation commit where
   practical. A successful Python HIL run does not substitute for exercising the
   Node adapter itself.

### Recorded Node I2C result

A bounded Node.js I2C example succeeded on **2026-08-02** against exact implementation
commit `6a30a322cdbc482a455df25dfdf03b076a66e299` on the dedicated Raspberry Pi 5
fixture:

- runtime: checksum-verified Node.js `v24.18.0` for Linux ARM64 with npm `11.16.0`;
- native backends: exact `i2c-bus@5.2.3` and `spi-device@3.1.2` packages built
  from the committed lockfile, followed by a successful native-module load check;
- transport: I2C bus 1, address `0x1D`, declared 100 kHz;
- acquisition: 8 samples captured, all 8 unique, with a measured temperature of
  `30.1934 °C`;
- cleanup: independent register readback confirmed standby, ±2 g, and default ODR.

The command ran as the non-root fixture account from a separate `/tmp` checkout and
exited within its 20-second outer timeout. No host name, private address, environment
dump, credential, or raw secret was recorded. This proves the maintained Node I2C
adapter and bounded example on the `0x1D` fixture only.

### Recorded Node SPI result

A bounded Node.js SPI example succeeded on **2026-08-05** against exact
implementation commit `ff4ff366ff021c5f446e324db8472d01b5613caf` on the dedicated
Raspberry Pi 5 fixture:

- runtime: Node.js `v24.16.0` for Linux ARM64 with npm `11.16.0`;
- native backends: exact `spi-device@3.1.2` and `i2c-bus@5.2.3` packages rebuilt
  from the committed lockfile, followed by a successful native-module load check;
- transport: `/dev/spidev0.0`, SPI Mode 0, 8-bit words, and 1 MHz;
- acquisition: 32 samples captured, all 32 unique, after the bounded 20 ms
  measurement settle, with a measured temperature of `29.3094 °C`;
- identity: `DEVID_AD=0xAD`, `DEVID_MST=0x1D`, `PARTID=0xED`, and `REVID=0x01`;
- cleanup: independent register readback confirmed `POWER_CTL=0x01`,
  `RANGE=0x81`, and `FILTER=0x00`, proving standby, ±2 g, and default ODR.

The command ran from a clean `git archive` of the exact commit, exited within its
20-second outer timeout, and closed its native descriptor. An earlier immediate
read produced an invalid `233.2873 °C` temperature and a startup-transition first
sample; that rejected run motivated the bounded settle helper and its ordering
regression test. No host name, private address, environment dump, credential, or
raw secret was recorded. This is Node adapter feature evidence and does not replace
the separate paired release-candidate SPI/I2C HIL requirement.

## FIFO physical validation plan

The C/Python FIFO API is currently supported by shared protocol vectors, mock
transports, sanitizer tests, and exact-length contract tests. Physical FIFO
validation is intentionally a later bounded run and is not claimed by this
change. Use a dedicated fixture run with all of the following controls:

1. Pin one exact commit, transport settings, range, and ODR; record identity and
   revision before configuration.
2. Configure a small FIFO watermark, enter measurement mode, and wait for a
   bounded number of expected sample periods without background threads.
3. Read `FIFO_ENTRIES` as axis locations and require a multiple of three no
   greater than 96; capture the raw count before every bounded read.
4. Read complete X/Y/Z samples from `FIFO_DATA`, confirm the x marker occurs only
   on the first location, virtual bits remain zero, and the reported count drops
   by exactly three locations per sample.
5. Repeat at signed orientations and compare FIFO samples with direct register
   samples within a fixture-owned timing tolerance.
6. Intentionally reach FIFO full/overrun in a bounded test, verify the documented
   error, then reset/flush the device rather than treating data after overrun as
   lossless.
7. Inject a transport failure after at least one complete sample and confirm the
   API reports the valid prefix and exact consumed-location count.
8. Restore standby, range, filter/ODR, FIFO watermark, and interrupt-map state;
   independently read back the final registers and store only sanitized evidence.

The run must never claim rollback of FIFO_DATA reads: successfully transferred
locations have already been popped by hardware.

## Release evidence policy

A production-ready claim requires recent successful HIL evidence for both a Linux
SPI fixture and a Linux I2C fixture. Each result must test the release-candidate
commit, record the device revision, be no more than 30 days old at release time,
and retain the corresponding workflow run/artifact link in the release record.
Where the target hardware permits changing `MISO/ASEL`, validate both I2C address
options before release.

Reference: Analog Devices, *ADXL354/ADXL355 Low Noise, Low Drift, Low Power,
3-Axis MEMS Accelerometers*, Rev. D, interface specifications and application
information.
