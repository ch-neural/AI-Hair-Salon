# Data Directory

This directory contains the application's data files.

## Files

### 📝 Configuration Files

- **`settings.json`** (gitignored)
  - Contains API keys and configuration
  - **NEVER commit this file to Git**
  - Copy from `settings.json.example` and fill in your API keys

- **`settings.json.example`**
  - Template for settings.json
  - Safe to commit to Git (no actual API keys)

### 📊 Database Files

- **`garments.json`** (gitignored)
  - Contains the hairstyle library data
  - Populated via admin dashboard

- **`garments.json.init`** or **`garments.json.clean`**
  - Initial/empty version for new installations
  - On first run, copy this to `garments.json`:
    ```bash
    cp data/garments.json.init data/garments.json
    # or
    cp data/garments.json.clean data/garments.json
    ```

- **`tryon_history.json`** (gitignored)
  - Contains the try-on history records
  - Automatically created on first try-on

- **`tryon_history.json.init`** or **`tryon_history.json.clean`**
  - Initial/empty version for new installations
  - On first run, copy this to `tryon_history.json`:
    ```bash
    cp data/tryon_history.json.init data/tryon_history.json
    # or
    cp data/tryon_history.json.clean data/tryon_history.json
    ```

## 🚀 First Time Setup

After cloning the repository, initialize the data files:

```bash
# 1. Create settings.json from example
cp data/settings.json.example data/settings.json

# 2. Edit settings.json and add your API keys
nano data/settings.json  # or use your preferred editor

# 3. Initialize database files
cp data/garments.json.init data/garments.json
cp data/tryon_history.json.init data/tryon_history.json

# 4. Start the application
./start.sh
```

## 🔒 Security

- ⚠️ **NEVER** commit `settings.json` to Git
- ⚠️ **NEVER** share your API keys publicly
- ✅ Only commit `.example`, `.init`, or `.clean` files

## 📦 Data Structure

### garments.json

```json
{
  "garments": [
    {
      "id": "unique-id",
      "name": "Short Curly Hair",
      "category": "short",
      "image_path": "garments/hairstyle_xxx.jpg",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "metadata": {
    "version": "1.0",
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

### tryon_history.json

```json
{
  "history": [
    {
      "id": "session-id",
      "user_photo_path": "static/inputs/user_xxx.jpg",
      "garment_id": "garment-id",
      "result_photo_path": "static/outputs/gen_xxx.jpg",
      "status": "success",
      "created_at": "2025-01-01T12:00:00Z"
    }
  ],
  "metadata": {
    "version": "1.0",
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

