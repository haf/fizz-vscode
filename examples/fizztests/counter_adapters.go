// Generated scaffold by fizzbee-mbt generator
// Source: ../counter.fizz
// Update the methods with your implementation.
package counter

import (
	mbt "github.com/fizzbee-io/fizzbee/mbt/lib/go"
)

// Role adaptors

// CounterRoleAdapter is a stub adaptor for CounterRole
type CounterRoleAdapter struct {
	value int
}

// Assert that CounterRoleAdapter satisfies CounterRole
var _ CounterRole = (*CounterRoleAdapter)(nil)

const MAX = 3

func (a *CounterRoleAdapter) ActionInc(args []mbt.Arg) (any, error) {
	// TODO: implement action Inc
	if a.value < MAX {
		a.value++
	}
	return nil, nil
}

func (a *CounterRoleAdapter) ActionGet(args []mbt.Arg) (any, error) {
	// TODO: implement action Get
	return a.value, nil
}

func (a *CounterRoleAdapter) ActionDec(args []mbt.Arg) (any, error) {
	// TODO: implement action Dec
	return nil, mbt.ErrNotImplemented
}

// Model adaptor
type CounterModelAdapter struct {
	counterRole *CounterRoleAdapter
}

// Assert that CounterModelAdapter satisfies CounterModel
var _ CounterModel = (*CounterModelAdapter)(nil)

// Constructor for CounterModelAdapter
func NewCounterModel() CounterModel {
	return &CounterModelAdapter{}
}

func GetTestOptions() map[string]any {
	return map[string]any{
		"max-seq-runs":      1000,
		"max-parallel-runs": 10000,
		"max-actions":       20,
	}
}

func (m *CounterModelAdapter) GetState() (map[string]any, error) {
	// TODO: implement GetState. Required.
	return nil, mbt.ErrNotImplemented
}

func (m *CounterModelAdapter) GetRoles() (map[mbt.RoleId]mbt.Role, error) {
	roles := map[mbt.RoleId]mbt.Role{
		{RoleName: "Counter", Index: 0}: m.counterRole,
	}
	return roles, nil

}

func (m *CounterModelAdapter) Init() error {
	m.counterRole = &CounterRoleAdapter{}
	return nil

}

func (m *CounterModelAdapter) Cleanup() error {
	// TODO: implement Cleanup
	return nil
}
