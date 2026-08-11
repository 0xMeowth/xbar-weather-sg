# Singapore Weather for macOS menu bar

An xbar plugin that shows the official two-hour forecast for one manually
selected Singapore area and alerts you to official nationwide heavy-rain
warnings.

## Features

- Select one forecast area from xbar's menu; the initial value is `Select an
  area`.
- Checks the official heavy-rain-warning feed every five minutes.
- Caches the two-hour forecast for 30 minutes, while still checking warnings
  on every run.
- Shows official warnings as national, unfiltered messages; it does not infer
  whether a warning applies to the selected area.
- Uses macOS notifications once per distinct active warning.
- No account or API key is needed. The plugin uses public endpoints from
  data.gov.sg and Meteorological Service Singapore (MSS).

## Privacy

- You select the forecast area manually. There is no real-area fallback.
- No IP lookup or IP-based geolocation is performed.
- The plugin never sends public IP address, Wi-Fi information, network
  identity, or any other location proxy to a service.
- Runtime requests are limited to the two official URLs listed below.
- xbar creates a local-only `*.vars.json` file after you select an area. Keep
  it private: do not commit or publish it, and add it to `.gitignore` if you
  keep the plugin in a Git repository. If you do not use Git, it stays on your
  computer by default and you do not need to do anything.

## Requirements

- macOS
- [xbar](https://xbarapp.com/)
- Python 3

## Tested on

- macOS 27.0 (build 26A5388g)
- xbar v2.1.7-beta
- Apple-provided Python 3.9.6

## Install

1. Download `xbar_weather_sg.5m.py`.
2. Copy it to xbar's plugin directory, `~/Library/Application Support/xbar/plugins`:

   ```sh
   cp xbar_weather_sg.5m.py ~/Library/Application\ Support/xbar/plugins/
   chmod +x ~/Library/Application\ Support/xbar/plugins/xbar_weather_sg.5m.py
   ```

3. Refresh xbar, then choose `<selected area>` from the plugin menu.

The filename's `5m` interval tells xbar to run the plugin every five minutes.

## Data and behavior

Forecast data comes from the official [data.gov.sg two-hour forecast API](https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast):

```text
https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast
```

No account or API key is required for the public requests used by this plugin.
data.gov.sg offers optional keys with higher rate limits; the unauthenticated
public limit is 6 requests per 10 seconds. The 30-minute forecast cache stays
below that limit during normal use.

Heavy-rain warnings come from the official [Meteorological Service Singapore feed](https://www.weather.gov.sg/files/rss/rssHeavyRain_new.xml):

```text
https://www.weather.gov.sg/files/rss/rssHeavyRain_new.xml
```

The forecast cache is refreshed no more than once every 30 minutes under
normal conditions. Warning polling remains on the five-minute schedule so a
new warning can appear within five minutes.

## Troubleshooting

- If the menu says `Select an area`, choose `<selected area>` in xbar's menu.
- If a forecast is stale or unavailable, refresh xbar and try again later;
  the plugin may keep the last cached forecast when the official endpoint is
  temporarily unavailable.
- If a warning notification is missed, allow xbar (or the process running the
  plugin) notification permission in macOS System Settings for future new or
  updated warnings. The same warning will not retry automatically. Warnings
  still appear in the xbar menu even when notification permission is
  unavailable.

## Test

From the development checkout, run:

```sh
python3 -m unittest discover -s tests -v
```

## License

MIT License

Copyright (c) 2026 0xMeowth

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
