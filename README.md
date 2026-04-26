# Network Visualizer

MacBook Air や Ubuntu 24 ノートPCの Wi-Fi からルータ、光回線、ISP、インターネットまでをローカルで計測して、ブラウザで見るための小さな診断ツールです。

## 最初の 5 分でわかる使い方

```bash
cd network-visualizer
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
netviz once
netviz serve --port 8765
```

ブラウザで http://localhost:8765 を開きます。継続計測しながら見る場合は別ターミナルで:

```bash
netviz collect --interval 30
```

または計測とサーバを同時に:

```bash
netviz collect --serve --interval 30
```

`netviz once --slow` は `traceroute` と `networkquality` も実行します。数十秒かかることがあります。

## Ubuntu 24 で使う

Ubuntu 24 では macOS コマンドではなく、主に次の標準系コマンドを使います。

| レイヤ | Ubuntu コマンド |
| --- | --- |
| Wi-Fi | `nmcli`, `iw`, `ip -4 addr` |
| LAN | `ip route`, `ping`, `ip neigh` |
| WAN | `curl`, `dig` または `resolvectl` / `getent` |
| 経路 | `traceroute` または `tracepath` |
| 品質 | `ping`, 任意で `speedtest` |

最小セット:

```bash
sudo apt update
sudo apt install -y python3-venv curl iproute2 iputils-ping network-manager wireless-tools iw
```

あると便利:

```bash
sudo apt install -y dnsutils traceroute iputils-tracepath
```

Ubuntu側でも同じように:

```bash
git clone <this-repo-url>
cd network-visualizer
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
netviz collect --serve --interval 30 --port 8765
```

ブラウザで http://localhost:8765 を開きます。

## MacBook Air と Ubuntu ノートの比較

1. 両方を同じSSID、同じ場所、同じ時間帯で接続します。
2. 両方で `netviz collect --serve --interval 30` を30分以上動かします。
3. 片方だけ `local_ip` / `gateway_ip` が消える、または `Gateway RTT` / loss が悪化するかを見ます。
4. MacBook Airだけ悪化し、Ubuntu側が安定している場合は、MacBook Air個体、macOS側設定、またはWi-Fiチップ周辺の疑いが強くなります。
5. 両方が同時に悪化する場合は、ルータ、回線、ISP、設置環境側の可能性が高いです。

CSV化:

```bash
netviz export --since 1d > netviz-$(hostname)-1d.csv
```

## 返品判断の見方

Wi-Fi の `RSSI` が近距離でも頻繁に `-75 dBm` 以下、または `SNR` が `20 dB` 未満に落ちる場合は、自機、設置場所、ルータ側の電波条件を疑います。同じ場所で別端末は安定し、この MacBook Air だけ悪いなら個体不良の可能性が上がります。

`Gateway RTT` や `gw_loss_pct` が悪い場合は、MacBook Air からルータまでの区間です。ここが悪いのに外部 ping だけを見ると、光回線やISPの問題に見えてしまいます。

`Gateway RTT` は安定しているのに `quality` の ping や `traceroute` の後段だけ悪い場合は、ルータ以降、光回線、ISP、相手先側の可能性が高いです。

切断が起きる時刻の前後で `metrics.db` に残った `wifi_metrics` と `lan_metrics` を見れば、電波低下、ルータ到達不能、外部だけ不調のどれかを切り分けやすくなります。

## コマンド

```bash
netviz once                    # 軽量計測を1回実行してJSON表示、DB保存
netviz once --slow             # traceroute / networkquality込み
netviz collect --interval 30   # 30秒ごとに軽量計測
netviz serve --port 8765       # ダッシュボード
netviz collect --serve         # 計測 + サーバ
netviz export --since 1d       # CSV出力
```

DB の場所は既定でカレントディレクトリの `metrics.db` です。変更する場合:

```bash
NETVIZ_DB=/path/to/metrics.db netviz collect
```

## sudo が必要なケース

既定では `sudo` が必要な `wdutil info` や `tcpdump` は使いません。macOSでは `networksetup`、`ipconfig`、`system_profiler`、`route`、`ping`、`arp`、`curl`、`dig`、`traceroute`、`networkquality` を使います。Ubuntuでは `nmcli`、`iw`、`ip`、`ping`、`curl`、`dig` / `resolvectl` / `getent`、`traceroute` / `tracepath` を使います。

## ipinfo の API キー

現状は API キーなしで `https://ipinfo.io/json` と `https://ipinfo.io/<ip>/json` を使います。traceroute の hop 逆引きは SQLite の `geo_cache` に 24 時間キャッシュします。無料枠を守るため、プライベートIPは問い合わせません。

## トラブルシュート

`dig` がない場合、UbuntuではシステムDNSのみ `resolvectl query` または `getent hosts` で測ります。`1.1.1.1` / `8.8.8.8` の個別比較をしたい場合は `sudo apt install dnsutils` を入れてください。

`system_profiler SPAirPortDataType -json` は数秒かかることがあります。`netviz once` が遅い場合でも、10秒前後なら正常範囲です。

ダッシュボードが空の場合は、先に `netviz once` または `netviz collect --interval 30` を実行してください。

CDN を使うため、ダッシュボードの Chart.js / Leaflet / D3 はインターネット接続がないと読み込めません。ネット切断中の完全オフライン表示が必要なら、JS/CSS をローカル同梱に変更してください。

UbuntuでWi-Fi情報が空になる場合は、NetworkManager管理外のインターフェースになっていないか確認してください。

```bash
nmcli device status
iw dev
```

## launchd サンプル

`~/Library/LaunchAgents/com.local.netviz.plist` に置く例です。パスは実際の venv に合わせてください。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.local.netviz</string>
  <key>ProgramArguments</key>
  <array>
    <string>/absolute/path/network-visualizer/.venv/bin/netviz</string>
    <string>collect</string>
    <string>--serve</string>
    <string>--interval</string>
    <string>30</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>WorkingDirectory</key><string>/absolute/path/network-visualizer</string>
</dict>
</plist>
```
