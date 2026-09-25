# Local AI website demo

A responsive, working landing page for Joey Rodriguez's practical local AI work. The visual was generated in AntLing Design Lab on Spark 2; the page adds editable HTML copy, navigation, and an interactive viewer for the separate model-produced layers.

## Run it

From this directory:

```sh
python3 -m http.server 8767 --bind 127.0.0.1
```

For a preview that stays available after closing Terminal, run `bash install_preview_macos.sh`. Open [http://127.0.0.1:8767/](http://127.0.0.1:8767/). The page's **Open the Lab** links point to the local AntLing Design Lab tunnel at `http://127.0.0.1:8765/`; they are intended for the local recording, not a public deployment.

## Recording path

1. Show the generated studio photo in AntLing Design Lab. The Design job is `0e0299c587d4408185cd911cd9b6909f`.
2. Show the separate layers in the Lab. The corrected Layer job is `1aff5074a9a94be78210b168d48b021d`.
3. Open this page and scroll from the live headline to the layer viewer. Select each layer with the buttons and download one of the transparent PNGs.
4. Resize the browser to show the same source visual and live copy adapting to a narrow layout.

The hero uses the original 2048px output. The split model ran at 1024px, and the viewer displays those actual raster layers. No image-generated lettering is used as page text.

This is a local demo site with no analytics, account, contact form, or external services. The only network-dependent link is the local Lab link.
