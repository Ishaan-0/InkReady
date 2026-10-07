import glob
import os
import shutil
import subprocess
import tempfile

# Paths
input_dir = os.path.expanduser("/Users/ishaan/Documents/Comics:Mangas/New-Comics")
output_dir = os.path.expanduser("/Users/ishaan/Documents/Comics:Mangas")

# ==============================================================================
# CHANGE 1: DE-DUPLICATE GLOB MATCHES
# The pattern *.epub automatically captures *.kepub.epub files. Using list(set(...))
# prevents processing the same .kepub.epub file twice in the loop.
# ==============================================================================
files = list(set(glob.glob(os.path.join(input_dir, "*.epub"))))

if not files:
  print(f"No .epub or .kepub.epub files found in: {input_dir}")
  exit(0)

print(f"Found {len(files)} unique file(s) to process.\n")

for file_path in files:
  filename = os.path.basename(file_path)

  if filename.startswith("._"):
    continue

  print(f"Processing: {filename}...")
  temp_dir = tempfile.mkdtemp()

  try:
    # 1. Extract EPUB/KEPUB archive
    subprocess.run(["unzip", "-q", file_path, "-d", temp_dir], check=True)

    # 2. Gather image files
    img_files = []
    for root, _, filenames in os.walk(temp_dir):
      for f in filenames:
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
          img_files.append(os.path.join(root, f))

    # 3. Apply ImageMagick adjustments in-place
    if img_files:
      print(f"  -> Enhancing {len(img_files)} images for Kobo Libra Colour...")

      # ==============================================================================
      # CHANGE 2: OPTIMIZED MAGICK COMMAND FOR KOBO LIBRA COLOUR
      # ==============================================================================
      cmd = [
          "magick",
          "mogrify",
          # 1. Force sRGB color space to prevent muted or incorrectly rendered colors
          "-colorspace",
          "sRGB",
          # 2. Downsample to Kobo Libra Colour screen resolution (1440x1920)
          #    Prevents live device CPU downsampling artifacts and speeds up reading
          "-resize",
          "1440x1920>",
          # 3. Lift gamma (+12%) to send more light through the Kaleido 3 color filter
          "-gamma",
          "1.12",
          # 4. Boost saturation to 138% while keeping lightness at 105%
          "-modulate",
          "105,138,100",
          # 5. Soften contrast curve (down from 3x50%) to prevent crushed shadows
          "-sigmoidal-contrast",
          "2.5x45%",
          # 6. Fine-tuned unsharp mask tailored for 150/300 PPI display
          "-unsharp",
          "0x0.8+0.8+0.005",
      ] + img_files

      subprocess.run(cmd, check=True)

    # 4. Repackage into a clean KEPUB/EPUB file
    out_path = os.path.join(output_dir, filename)
    if os.path.exists(out_path):
      os.remove(out_path)

    mimetype_file = os.path.join(temp_dir, "mimetype")
    if os.path.exists(mimetype_file):
      # mimetype must be uncompressed (-X0) and first for valid EPUB compliance
      subprocess.run(
          ["zip", "-q", "-X0", out_path, "mimetype"], cwd=temp_dir, check=True
      )
      subprocess.run(
          ["zip", "-q", "-rg", out_path, ".", "-x", "*.DS_Store", "mimetype"],
          cwd=temp_dir,
          check=True,
      )
    else:
      subprocess.run(
          ["zip", "-q", "-r", out_path, ".", "-x", "*.DS_Store"],
          cwd=temp_dir,
          check=True,
      )

    print(f"Finished: {filename}\n")

  except Exception as e:
    print(f"Error processing {filename}: {e}\n")

  finally:
    # Clean up temporary working directory
    shutil.rmtree(temp_dir)

print(f"All processing complete! Files saved to:\n{output_dir}")