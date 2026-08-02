const spiImport = await import("spi-device");
const i2cImport = await import("i2c-bus");
const spi = spiImport.default ?? spiImport;
const i2c = i2cImport.default ?? i2cImport;

if (typeof spi.open !== "function") throw new Error("spi-device did not expose open()");
if (typeof i2c.openPromisified !== "function") {
  throw new Error("i2c-bus did not expose openPromisified()");
}
console.log("validated optional native modules");
