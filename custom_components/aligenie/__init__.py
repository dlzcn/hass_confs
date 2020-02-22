#!/usr/bin/env python3
# encoding: utf-8
import json
import logging

_LOGGER = logging.getLogger(__name__)

_hass = None
_restApi = None
_restToken = None

_CHECK_ALIAS = False  # 仅显示有效的天猫精灵设备名称（初次为了验证名称是否正确，请打开此开关）


def hassRest(cmd, data=None):
    import requests

    url = _restApi + cmd
    method = 'POST' if data else 'GET'
    _LOGGER.debug('REST %s %s %s', method, url, data or '')

    headers = {'Authorization': 'Bearer ' + _restToken,
               'Content-Type': 'application/json'} if _restToken else None
    result = requests.request(method, url, data=data,
                              headers=headers, timeout=3).text
    #_LOGGER.info('REST RESPONSE: %s', result)
    return json.loads(result)


def hassStates():
    if _hass:
        return _hass.states.async_all()

    states = []
    from collections import namedtuple
    for d in hassRest('states'):
        states.append(namedtuple('EntityState', d.keys())(*d.values()))
    return states


def hassState(entity_id):
    if _hass:
        return _hass.states.get(entity_id)

    from collections import namedtuple
    d = hassRest('states/' + entity_id)
    return namedtuple('EntityState', d.keys())(*d.values())


async def hassService(domain, service, data):
    if _hass:
        with AsyncTrackStates(_hass) as changed_states:
            return await _hass.services.async_call(domain, service, data, True)

    return hassRest('services/' + domain + '/' + service, data)


async def validateToken(payload):
    """Validate access token or rest api information"""
    accessToken = payload.get('accessToken')

    if _hass:
        token = await _hass.auth.async_validate_access_token(accessToken)
        return token is not None

    if accessToken.startswith('http'):
        global _restApi
        global _restToken
        global _CHECK_ALIAS
        parts = accessToken.split('_')
        _CHECK_ALIAS = parts[1][-1:].isupper()   # Trick
        _restApi = parts[0] + '://' + parts[1] + ':' + parts[2] + '/api/'
        _restToken = parts[3]
        _LOGGER.debug('REST URL: %s, TOKEN: %s', _restApi, _restToken)
        return True

    return False


def errorResult(errorCode, messsage=None):
    """Generate error result"""
    messages = {
        'INVALIDATE_CONTROL_ORDER':    'invalidate control order',
        'SERVICE_ERROR': 'service error',
        'DEVICE_NOT_SUPPORT_FUNCTION': 'device not support',
        'INVALIDATE_PARAMS': 'invalidate params',
        'DEVICE_IS_NOT_EXIST': 'device is not exist',
        'IOT_DEVICE_OFFLINE': 'device is offline',
        'ACCESS_TOKEN_INVALIDATE': ' access_token is invalidate'
    }
    return {'errorCode': errorCode, 'message': messsage if messsage else messages[errorCode]}


async def handleRequest(data):
    """Handle request"""
    try:
        header = data['header']
        payload = data['payload']
        properties = None
        name = header['name']
        _LOGGER.info("Handle Request: %s", data)

        if await validateToken(payload):
            namespace = header['namespace']
            if namespace == 'AliGenie.Iot.Device.Discovery':
                result = discoveryDevice()
            elif namespace == 'AliGenie.Iot.Device.Control':
                result = await controlDevice(name, payload)
            elif namespace == 'AliGenie.Iot.Device.Query':
                result = queryDevice(name, payload)
                if not 'errorCode' in result:
                    properties = result
                    result = {}
            else:
                result = errorResult('SERVICE_ERROR')
        else:
            result = errorResult('ACCESS_TOKEN_INVALIDATE')

        # Check error and fill response name
        header['name'] = (
            'Error' if 'errorCode' in result else name) + 'Response'

        # Fill response deviceId
        if 'deviceId' in payload:
            result['deviceId'] = payload['deviceId']

        response = {'header': header, 'payload': result}
        if properties:
            response['properties'] = properties
        #_LOGGER.info("Respnose: %s", response)
        return response
    except:
        import traceback
        _LOGGER.error(traceback.format_exc())
        return {'header': {'name': 'errorResult'}, 'payload': errorResult('SERVICE_ERROR', 'service exception')}


def discoveryDevice():
    # 因为天猫精灵不会经常调用发现协议，每次发现后释放以节约内存
    from urllib.request import urlopen
    places = json.loads(urlopen(
        'https://open.bot.tmall.com/oauth/api/placelist').read().decode('utf-8'))['data']
    if _CHECK_ALIAS:
        aliases = json.loads(urlopen(
            'https://open.bot.tmall.com/oauth/api/aliaslist').read().decode('utf-8'))['data']
        aliases.append({'key': '电视', 'value': ['电视机']})
    else:
        aliases = None

    states = hassStates()

    groups_ttributes = groupsAttributes(states)

    devices = []
    for state in states:
        attributes = state.attributes

        if attributes.get('hidden') or attributes.get('hagenie_hidden'):
            continue

        friendly_name = attributes.get('friendly_name')
        if friendly_name is None:
            continue

        entity_id = state.entity_id
        deviceType = guessDeviceType(entity_id, attributes)
        if deviceType is None:
            continue

        deviceName = guessDeviceName(entity_id, attributes, places, aliases)
        if deviceName is None:
            continue

        zone = guessZone(entity_id, attributes, groups_ttributes, places)
        if zone is None:
            continue

        prop, action = guessPropertyAndAction(
            entity_id, attributes, state.state)
        if prop is None:
            continue

        # Merge all sensors into one for a zone
        # https://bbs.hassbian.com/thread-2982-1-1.html
        if deviceType == 'sensor':
            for sensor in devices:
                if sensor['deviceType'] == 'sensor' and zone == sensor['zone']:
                    deviceType = None
                    if not action in sensor['actions']:
                        sensor['properties'].append(prop)
                        sensor['actions'].append(action)
                        sensor['model'] += ' ' + friendly_name
                        # SHIT, length limition in deviceId: sensor['deviceId'] += '_' + entity_id
                    else:
                        _LOGGER.info('SKIP: ' + entity_id)
                    break
            if deviceType is None:
                continue
            deviceName = '传感器'
            entity_id = zone

        devices.append({
            'deviceId': entity_id,
            'deviceName': deviceName,
            'deviceType': deviceType,
            'zone': zone,
            'model': friendly_name,
            'brand': 'HomeAssistant',
            'icon': 'https://home-assistant.io/images/favicon-192x192.png',
            'properties': [prop],
            'actions': ['TurnOn', 'TurnOff', 'Query', action] if action == 'QueryPowerState' else ['Query', action],
            # 'extensions':{'extension1':'','extension2':''}
        })

        #_LOGGER.debug(str(len(devices)) + '. ' + deviceType + ':' + zone + '/' + deviceName + ((' <= ' + friendly_name) if friendly_name != deviceName else ''))

    # for sensor in devices:
        # if sensor['deviceType'] == 'sensor':
        # _LOGGER.info(json.dumps(sensor, indent=2, ensure_ascii=False))

    return {'devices': devices}


async def controlDevice(name, payload):
    entity_id = payload['deviceId']
    service = getControlService(name)
    domain = entity_id[:entity_id.find('.')]
    data = {"entity_id": entity_id}
    if domain == 'cover':
        service = 'close_cover' if service == 'turn_off' else 'open_cover'

    result = await hassService(domain, service, data)

    return {} if result else errorResult('IOT_DEVICE_OFFLINE')


def queryDevice(name, payload):
    deviceId = payload['deviceId']

    if payload['deviceType'] == 'sensor':

        states = hassStates()

        entity_ids = []
        for state in states:
            attributes = state.attributes
            if state.entity_id.startswith('group.') and (attributes['friendly_name'] == deviceId or attributes.get('hagenie_zone') == deviceId):
                entity_ids = attributes.get('entity_id')
                break

        properties = [{'name': 'powerstate', 'value': 'on'}]
        for state in states:
            entity_id = state.entity_id
            attributes = state.attributes
            if entity_id.startswith('sensor.') and (entity_id in entity_ids or attributes['friendly_name'].startswith(deviceId) or attributes.get('hagenie_zone') == deviceId):
                prop, action = guessPropertyAndAction(
                    entity_id, attributes, state.state)
                if prop is None:
                    continue
                properties.append(prop)
        return properties
    else:
        state = hassState(deviceId)
        if state is not None or state.state != 'unavailable':
            return {'name': 'powerstate', 'value': 'off' if state.state == 'off' else 'on'}
    return errorResult('IOT_DEVICE_OFFLINE')


def getControlService(action):
    i = 0
    service = ''
    for c in action:
        service += (('_' if i else '') + c.lower()) if c.isupper() else c
        i += 1
    return service


DEVICE_TYPES = [
    'television',  # : '电视',
    'light',  # : '灯',
    'aircondition',  # : '空调',
    'airpurifier',  # : '空气净化器',
    'outlet',  # : '插座',
    'switch',  # : '开关',
    'roboticvacuum',  # : '扫地机器人',
    'curtain',  # : '窗帘',
    'humidifier',  # : '加湿器',
    'fan',  # : '风扇',
    'bottlewarmer',  # : '暖奶器',
    'soymilkmaker',  # : '豆浆机',
    'kettle',  # : '电热水壶',
    'waterdispenser',  # : '饮水机',
    'camera',  # : '摄像头',
    'router',  # : '路由器',
    'cooker',  # : '电饭煲',
    'waterheater',  # : '热水器',
    'oven',  # : '烤箱',
    'waterpurifier',  # : '净水器',
    'fridge',  # : '冰箱',
    'STB',  # : '机顶盒',
    'sensor',  # : '传感器',
    'washmachine',  # : '洗衣机',
    'smartbed',  # : '智能床',
    'aromamachine',  # : '香薰机',
    'window',  # : '窗',
    'kitchenventilator',  # : '抽油烟机',
    'fingerprintlock',  # : '指纹锁',
    'telecontroller',  # : '万能遥控器',
    'dishwasher',  # : '洗碗机',
    'dehumidifier',  # : '除湿机',
    'dryer',  # : '干衣机',
    'wall-hung-boiler',  # : '壁挂炉',
    'microwaveoven',  # : '微波炉',
    'heater',  # : '取暖器',
    'mosquito-dispeller',  # : '驱蚊器',
    'treadmill',  # : '跑步机',
    'smart-gating',  # : '智能门控(门锁)',
    'smart-band',  # : '智能手环',
    'hanger',  # : '晾衣架',
]

INCLUDE_DOMAINS = {
    'climate': 'aircondition',
    'fan': 'fan',
    'sensor': 'sensor',
    'light': 'light',
    'media_player': 'television',
    'remote': 'telecontroller',
    'switch': 'switch',
    'vacuum': 'roboticvacuum',
    'cover': 'curtain',
}

EXCLUDE_DOMAINS = [
    'automation',
    'binary_sensor',
    'device_tracker',
    'group',
    'zone',
]


def guessDeviceType(entity_id, attributes):
    # http://doc-bot.tmall.com/docs/doc.htm?treeId=393&articleId=108271&docType=1

    if 'hagenie_deviceType' in attributes:
        return attributes['hagenie_deviceType']

    # Exclude with domain
    domain = entity_id[: entity_id.find('.')]
    if domain in EXCLUDE_DOMAINS:
        return None

    # Map from domain
    return INCLUDE_DOMAINS[domain] if domain in INCLUDE_DOMAINS else None


def guessDeviceName(entity_id, attributes, places, aliases):
    if 'hagenie_deviceName' in attributes:
        return attributes['hagenie_deviceName']

    # Remove place prefix
    name = attributes['friendly_name']
    for place in places:
        if name.startswith(place):
            name = name[len(place):]
            break

    if aliases is None or entity_id.startswith('sensor'):
        return name

    # Name validation
    for alias in aliases:
        if name == alias['key'] or name in alias['value']:
            return name

    _LOGGER.error(
        '%s is not a valid name in https://open.bot.tmall.com/oauth/api/aliaslist', name)
    return None


def groupsAttributes(states):
    groups_attributes = []
    for state in states:
        group_entity_id = state.entity_id
        # and not group_entity_id.startswith('group.all_')
        if group_entity_id != 'group.default_view' and group_entity_id.startswith('group.'):
            group_attributes = state.attributes
            if 'entity_id' in group_attributes:
                groups_attributes.append(group_attributes)
    return groups_attributes

# https://open.bot.tmall.com/oauth/api/placelist


def guessZone(entity_id, attributes, groups_attributes, places):
    if 'hagenie_zone' in attributes:
        return attributes['hagenie_zone']

    # Guess with friendly_name prefix
    name = attributes['friendly_name']
    for place in places:
        if name.startswith(place):
            return place

    # Guess from HomeAssistant group
    for group_attributes in groups_attributes:
        for child_entity_id in group_attributes['entity_id']:
            if child_entity_id == entity_id:
                if 'hagenie_zone' in group_attributes:
                    return group_attributes['hagenie_zone']
                return group_attributes['friendly_name']

    return None


def guessPropertyAndAction(entity_id, attributes, state):
    # http://doc-bot.tmall.com/docs/doc.htm?treeId=393&articleId=108264&docType=1
    # http://doc-bot.tmall.com/docs/doc.htm?treeId=393&articleId=108268&docType=1
    # Support On/Off/Query only at this time
    if 'hagenie_propertyName' in attributes:
        name = attributes['hagenie_propertyName']

    elif entity_id.startswith('sensor.'):
        unit = attributes['unit_of_measurement'] if 'unit_of_measurement' in attributes else ''
        if unit == u'°C' or unit == u'℃':
            name = 'Temperature'
        elif unit == 'lx' or unit == 'lm':
            name = 'Brightness'
        elif ('hcho' in entity_id):
            name = 'Fog'
        elif ('humidity' in entity_id):
            name = 'Humidity'
        elif ('pm25' in entity_id):
            name = 'PM2.5'
        elif ('co2' in entity_id):
            name = 'WindSpeed'
        else:
            return (None, None)
    else:
        name = 'PowerState'
        if state != 'off':
            state = 'on'
    return ({'name': name.lower(), 'value': state}, 'Query' + name)


async def main():
    import os
    import sys
    try:
        REQUEST_METHOD = os.getenv('REQUEST_METHOD')
        if REQUEST_METHOD == 'POST':
            data = json.load(sys.stdin)
            _LOGGER.debug(json.dumps(_request, indent=2))
        else:
            data = {
                'header': {'namespace': 'AliGenie.Iot.Device.Discovery', 'name': 'DiscoveryDevices', 'messageId': 'd0c17289-55df-4c8c-955f-b735e9bdd305'},
                # 'header': {'namespace': 'AliGenie.Iot.Device.Control', 'name': 'TurnOn', 'messageId': 'd0c17289-55df-4c8c-955f-b735e9bdd305'},
                # 'header': {'namespace': 'AliGenie.Iot.Device.Query', 'name': 'Query', 'messageId': 'd0c17289-55df-4c8c-955f-b735e9bdd305'},
                'payload': {'accessToken': sys.argv[1] if len(sys.argv) > 1 else 'https_192.168.1.10_8123_token', 'deviceId': 'weather.caiyun', 'deviceType': 'sensor'}
            }
        response = await handleRequest(data)
    except:
        import traceback
        _LOGGER.error(traceback.format_exc())
        response = {'header': {'name': 'errorResult'},
                    'payload': errorResult('SERVICE_ERROR', 'json error')}

    print('Content-Type: application/json\r\n')
    print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    import asyncio
    _LOGGER.setLevel(logging.DEBUG)
    _LOGGER.addHandler(logging.StreamHandler())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
    exit(0)

from datetime import timedelta
from typing import Optional
from homeassistant.helpers.state import AsyncTrackStates
import homeassistant.auth.models as models
from homeassistant.auth.const import ACCESS_TOKEN_EXPIRATION
from homeassistant.components.http import HomeAssistantView

MAIN = 'aligenie'
DOMAIN = 'aligenie'
EXPIRE_HOURS = 8760  # 365天过期


async def async_setup(hass, config):
    global _hass
    _hass = hass
    hass.auth._store.async_create_refresh_token = async_create_refresh_token
    hass.http.register_view(AliGenieView)
    return True


class AliGenieView(HomeAssistantView):
    """View to handle Configuration requests."""

    url = '/aligenie'
    name = 'aligenie'
    requires_auth = False

    async def post(self, request):
        """Update state of entity."""
        data = await request.json()
        response = await handleRequest(data)
        return self.json(response)


async def async_create_refresh_token(
        user: models.User, client_id: Optional[str] = None,
        client_name: Optional[str] = None,
        client_icon: Optional[str] = None,
        token_type: str = models.TOKEN_TYPE_NORMAL,
        access_token_expiration: timedelta = ACCESS_TOKEN_EXPIRATION) -> models.RefreshToken:
    if access_token_expiration == ACCESS_TOKEN_EXPIRATION:
        access_token_expiration = timedelta(hours=EXPIRE_HOURS)
    _LOGGER.info('Access token expiration: %d hours', EXPIRE_HOURS)
    """Create a new token for a user."""
    kwargs = {
        'user': user,
        'client_id': client_id,
        'token_type': token_type,
        'access_token_expiration': access_token_expiration
    }  # type: Dict[str, Any]
    if client_name:
        kwargs['client_name'] = client_name
    if client_icon:
        kwargs['client_icon'] = client_icon

    refresh_token = models.RefreshToken(**kwargs)
    user.refresh_tokens[refresh_token.id] = refresh_token

    _hass.auth._store._async_schedule_save()
    return refresh_token

