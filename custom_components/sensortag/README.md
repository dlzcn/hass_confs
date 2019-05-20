# TI Sensortag sensor (CC2650)

## 使用方法：

- 在HA中建立以下路径 `home assistant\custom_components\sensortag`
- 在系统上安装 bluepy，本模块依赖于 bluepy 1.6.0
  ```shell
  $ sudo apt-get install python-pip libglib2.0-dev
  $ sudo pip install bluepy
  ```

- 在 sensortag 文件夹下放入 sensor.py 文件。
- 在 configuration.yaml 或者其他对应文件中配置 sensor。

## 配置内容如下

``` yaml
sensor:
  - platform: sensortag
    name: storage_room
    mac: xx:xx:xx:xx:xx:xx
    median: 3 #中值滤波参数
    scan_interval: 10  # 数据刷新间隔，单位是秒
    monitored_conditions:
      - temperature
      - illuminance
      - humidity
      - pressure
      - battery

```