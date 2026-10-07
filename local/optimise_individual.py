import argparse
import os
import shutil
import subprocess
import tempfile

# Destination directory
DEST_DIR = os.path.expanduser("~/Documents/Comics/Mangas")
os.makedirs(DEST_DIR, exist_ok=True)


def extract_archive(file_path, extract_dir):
  """Extracts ZIP, CBZ, RAR, CBR, or 7Z archives."""
  ext = os.path.splitext(file_path)[1].lower()

  if ext in [".cbz", ".zip", ".epub"]:
    subprocess.run(["unzip", "-q", file_path, "-d", extract_dir], check=True)
  elif ext in [".cbr", ".rar"]:
    # Requires unar (brew install unar)
    subprocess.run(
        ["unar", "-q", "-o", extract_dir, file_path, "-f"], check=True
    )
  elif ext in [".7z", ".cb7"]:
    subprocess.run(
        ["7z", "x", f"-o{extract_dir}", file_path, "-y"], check=True
    )
  else:
    raise ValueError(f"Unsupported archive format: {ext}")


def process_comic(input_path):
  input_path = os.path.expanduser(input_path.strip().strip("'\""))

  if not os.path.exists(input_path):
    print(f"Error: Path does not exist: {input_path}")
    return

  base_name = os.path.splitext(os.path.basename(input_path))[0]
  # Remove trailing extensions if double-named (e.g. file.kepub.epub)
  if base_name.endswith(".kepub"):
    base_name = os.path.splitext(base_name)[0]

  output_filename = f"{base_name}.kepub.epub"
  final_output_path = os.path.join(DEST_DIR, output_filename)

  print(f"\nProcessing: {os.path.basename(input_path)}")
  temp_dir = tempfile.mkdtemp()

  try:
    # 1. Extract files
    if os.path.isdir(input_path):
      # If user passed a folder of images directly
      for item in os.listdir(input_path):
        s = os.path.join(input_path, item)
        d = os.path.join(temp_dir, item)
        if os.path.isdir(s):
          shutil.copytree(s, d)
        else:
          shutil.copy2(s, d)
    else:
      extract_archive(input_path, temp_dir)

    # 2. Collect image files across all extracted subfolders
    img_files = []
    for root, _, filenames in os.walk(temp_dir):
      for f in filenames:
        if f.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
        ):
          img_files.append(os.path.join(root, f))

    if not img_files:
      print("No images found inside archive. Skipping.")
      return

    print(f"  -> Optimizing {len(img_files)} pages with ImageMagick...")

    # Batch process in chunks of 100 to avoid shell argument length limits
    chunk_size = 100
    for i in range(0, len(img_files), chunk_size):
      chunk = img_files[i : i + chunk_size]
      cmd = [
          "magick",
          "mogrify",
          "-modulate",
          "100,125,100",
          "-sigmoidal-contrast",
          "3x50%",
          "-unsharp",
          "0x0.75+0.75+0.008",
      ] + chunk
      subprocess.run(cmd, check=True)

    # 3. Repackage into a KEPUB-compliant EPUB container
    print(f"  -> Packaging into {output_filename}...")
    if os.path.exists(final_output_path):
      os.remove(final_output_path)

    mimetype_file = os.path.join(temp_dir, "mimetype")
    if os.path.exists(mimetype_file):
      subprocess.run(
          ["zip", "-q", "-X0", final_output_path, "mimetype"],
          cwd=temp_dir,
          check=True,
      )
      subprocess.run(
          [
              "zip",
              "-q",
              "-rg",
              final_output_path,
              ".",
              "-x",
              "*.DS_Store",
              "mimetype",
          ],
          cwd=temp_dir,
          check=True,
      )
    else:
      subprocess.run(
          ["zip", "-q", "-r", final_output_path, ".", "-x", "*.DS_Store"],
          cwd=temp_dir,
          check=True,
      )

    print(f"Done! Saved to: {final_output_path}")

  except Exception as e:
    print(f"Failed to process {input_path}: {e}")
  finally:
    shutil.rmtree(temp_dir)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Convert comic archives to optimized KEPUB"
  )
  parser.add_argument("path", help="Path to .cbz, .cbr, .zip, or folder")
  args = parser.parse_args()

  process_comic(args.path)