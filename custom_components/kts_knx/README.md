# KTS KNX — 迁移说明（旧 knx 插件 → 新版 Home Assistant）

本目录是把仓库根目录 `custom_components/knx`（HA 0.9x / xknx 0.11 时代的定制 KNX 集成）
迁移到新版 Home Assistant（2024.4+，已验证到 2026.2）后的新插件。
集成域名改为 **`kts_knx`**，避免与新版 HA 内置的 `knx` 集成（现在是 config-flow、
占用 `knx` 域名、固定 `xknx==3.20.0`）冲突。

## 安装

1. 把 `custom_components/kts_knx/` 整个目录复制到新 HA 的
   `config/custom_components/kts_knx/`。
2. 依赖 xknx 3.x 由 manifest.json 声明（`xknx>=3.0.0,<4.0`），HA 启动时会自动安装。
3. 旧的 `custom_components/knx/` 目录**不要再复制**到新 HA。

## 配置改动

### configuration.yaml

旧：

```yaml
knx:
  config_file: 'domains/xknx.yaml'
  tunneling:
    host: !secret knx_router_ip
```

新（只改域名）：

```yaml
kts_knx:
  config_file: 'domains/xknx.yaml'   # 老的 xknx.yaml 继续用，不用改
  tunneling:
    host: !secret knx_router_ip
    # local_ip: ...                   # 可选
  # routing:                          # 或者路由方式
  #   local_ip: ...
  # fire_event: true                  # 可选，产生 kts_knx_event 事件
  # fire_event_filter:
  #   - '3/0/#'
  # rate_limit: 20
  # own_address: '1.2.222'            # 原 xknx.yaml general.own_address 改放这里
```

注意：新版 xknx 不再解析 xknx.yaml 里的 `general:` 段，`own_address`
请放到上面的 `kts_knx.own_address`。

### climate / cover（KTS 非标空调与窗帘）

`domains/climate.yaml`、`domains/cover.yaml` 里的条目只改 `platform: knx` →
`platform: kts_knx`，其余字段（`temperature_address`、`move_long_address`、
`travelling_time_down` 等）**完全不变**。

### light / switch / scene / binary_sensor / notify / sensor

这些设备仍然由 `domains/xknx.yaml` 的 `groups:` 段驱动，字段名不变，
无需改动。

### 服务与事件

- 旧 `knx.send` → 新 `kts_knx.send`（参数 `address` / `payload` 不变）。
- 旧 `knx_event` → 新 `kts_knx_event`。

## 非标 KNX 设备的处理（全部保留）

1. **窗帘 position 反馈（`_kts_cover.py`）**：KTS 窗帘在 move_long 同一地址
   上用 DPT 1.00x（1 bit）回报位置。收到 `DPTBinary(1)`/`(0)` 时改写成
   `DPTArray(255)`/`(0)` 再交给 DPT 5.001 位置解析；语义为 raw 255 = 全闭 =
   HA position 0，raw 0 = 全开 = position 100（与老实现一致）。
2. **空调运行模式（`_kts_climate.py`）**：DPT 1count 厂商自定义编码
   Cool=1 / Dry=2 / Fan=3 / Heat=4；风速 Low=1 / Medium=2 / High=3 / Auto=4。
3. **开关量 on/off**：普通 DPT 1.001。

## 相比旧版的 API 适配点（均已对照 HA core dev 分支与 xknx 3.20 验证）

- xknx 3.x：`RemoteValue1Count` → `RemoteValueDptValue1Ucount`；
  报文 payload 变为 `GroupValueWrite/GroupValueResponse`；
  `Device` 新增抽象方法 `_iter_remote_values`；
  `process_group_write/response` 与 RemoteValue 调用改为同步；
  设备注册用 `xknx.devices.async_add()`；
  `BinarySensor` 不再有 `device_class` 参数（改在 HA 实体上设置）。
- HA 实体 API：`LightEntity` 需要 `color_mode/supported_color_modes`；
  `SwitchEntity`；`CoverEntityFeature`（含 `is_opening/is_closing`）；
  `ClimateEntityFeature.TARGET_TEMPERATURE|FAN_MODE` + `HVACMode`；
  `SensorEntity.native_value/native_unit_of_measurement`；
  `Scene.async_activate` 仍可用（服务走 `_async_activate`）。
- `notify:` YAML 平台（`BaseNotificationService`）在新版仍支持（内部为
  `notify.legacy`），如未来被移除，可把 knx 通知改用脚本 + `kts_knx.send`。
- 旧版 `knx.expose`（把 HA 实体值暴露回总线）与 binary_sensor `automation:`
  （KNX 触发脚本）本次未迁移：当前配置未使用；如需要，前者可用新版内置
  knx 集成或脚本 `kts_knx.send` 替代，后者建议直接用 HA 自动化监听
  binary_sensor 状态。

## 已验证

- 所有模块在 HA 2026.2.3 + xknx 3.20 下导入通过。
- 用真实 `domains/xknx.yaml` 端到端加载：11 灯 / 3 开关 / 10 场景 /
  1 二进制传感器，与原配置一致。
- 非标逻辑冒烟测试通过：DPT1→DPT5.001 位置转换、DPT1 标准字节位置、
  运行/风扇模式双向映射、on/off、set_position 行程推算与 stop。
