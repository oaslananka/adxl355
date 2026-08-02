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

The workflow accepts declared bus rates of 100 kHz, 400 kHz, 1 MHz, or 3.4 MHz.
Linux adapters do not provide a portable API for changing the controller clock,
so configure the bus speed in the host platform and pass the matching declared
value to the workflow. Test both `0x1D` and `0x53` when the product fixture
supports changing the strap.

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

## Local opt-in execution

Install only the selected adapter and run the command explicitly. These commands
are not part of normal `pytest` discovery.

```bash
python -m pip install --no-deps -e ./python

# SPI example: /dev/spidev0.0, Mode 0, 1 MHz
python -m pip install spidev==3.8
python scripts/hil_runner.py \
  --transport spi \
  --spi-bus 0 \
  --spi-device 0 \
  --spi-speed-hz 1000000 \
  --samples 32 \
  --report artifacts/hil-report.json

# I2C example: /dev/i2c-1, address 0x1D
python -m pip install smbus2==0.6.1
python scripts/hil_runner.py \
  --transport i2c \
  --i2c-bus 1 \
  --i2c-address 0x1D \
  --i2c-bus-hz 400000 \
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

This result proves the integrated SPI path and runner setup. It is not the final
release-candidate evidence because documentation and governance changes may move
the candidate commit. A successful I2C run is still pending. Before publication,
run both transports against the same final release-candidate SHA.

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
