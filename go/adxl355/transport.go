package adxl355

// Transport is the abstract bus interface for ADXL355 communication.
type Transport interface {
	// ReadRegister must return exactly length bytes or a non-nil error.
	// Zero-length, truncated, and overlong success payloads violate the contract.
	ReadRegister(reg byte, length int) ([]byte, error)
	// WriteRegister must write the complete payload or return a non-nil error.
	WriteRegister(reg byte, data []byte) error
	// DelayMs blocks for ms milliseconds.
	DelayMs(ms uint32)
}
