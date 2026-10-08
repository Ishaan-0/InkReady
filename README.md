# InkReady

Batch-optimize EPUBs and KEPUBs for e-readers. Resizes images, adjusts gamma, brightness, saturation, contrast, and sharpness — tuned per device.

Supports Kobo Libra Colour, Kindle Colorsoft, Kindle Scribe, reMarkable Paper Pro, and more.

---

## Download

Grab the latest release for your platform from the [Releases](../../releases) page — available for macOS, Windows, and Linux.

---

## Installing on macOS

macOS will flag InkReady as unverified since it isn't signed with an Apple developer certificate. Here's how to get past that:

1. Download the `.zip` from the Releases page and unzip it
2. Open the `InkReady` folder → go into `dist/`
3. Double-click `InkReady.app` — macOS will show a popup with **Move to Trash** as the only option, just close that window
4. Open **System Settings → Privacy & Security** and scroll down — you'll see a message about InkReady being blocked
5. Click **Open Anyway**
6. Move `InkReady.app` from `InkReady/dist/` to your **Applications** folder

The app will open normally from Applications every time after that.

---

## Folder Structure

```
InkReady/
├── local/        personal scripts i run on my own machine (requires ImageMagick via Homebrew)
├── src/          source code for the distributable app
├── build/        bundled releases for macOS, Windows, and Linux
└── assets/       icons and images
```
