""" Turn off lights that are on. """

lights = []

for state in hass.states.all():
    if state.entity_id.startswith('light.') and state.state == 'on':
        lights.append(state.entity_id)

if lights:
    data = {'entity_id': lights}
    hass.services.call('light', 'turn_off', data)