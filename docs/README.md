# Documentation

Additional technical documentation for AI-Hair-Salon.

## Architecture

### Two-Stage Mode

See [README_TWO_STAGE_MODE.md](README_TWO_STAGE_MODE.md) for detailed information about the two-stage AI generation process.

**Summary**:
- **Stage 1**: Gemini LLM analyzes images and generates a text description focusing only on hair
- **Stage 2**: Gemini Image Model generates the final image based on the description

This approach provides superior control over single-stage generation, ensuring only the hairstyle changes while preserving face, body, clothing, and background.

## Configuration

Configuration is managed through `data/settings.json`. See `data/settings.json.example` for a template.

Key settings:
- `GEMINI_API_KEY`: Your Gemini API key
- `GEMINI_MODEL`: Image generation model (default: `gemini-2.5-flash-image`)
- `GEMINI_LLM`: Text analysis model (default: `gemini-2.5-flash`)
- `VENDOR_TRYON`: Try-on service provider (default: `Gemini`)
- `LLM_ENABLED`: Enable/disable photo validation (default: `true`)

## API Reference

### Try-On API

**Endpoint**: `POST /api/try-on`

**Request**:
```json
{
  "user_photo": "data:image/jpeg;base64,...",
  "garment_image_url": "/static/garments/hairstyle.jpg"
}
```

**Response**:
```json
{
  "status": "pending",
  "session_id": "tryon_123456789"
}
```

**Poll Status**: `GET /api/try-on/{session_id}`

**Response**:
```json
{
  "status": "ok",
  "output": "/static/outputs/gen_123456789.jpg",
  "before_url": "/static/inputs/user_123456789.jpg",
  "comparison_url": "/static/outputs/comparison_123456789.jpg"
}
```

## Contributing

Contributions are welcome! Please see the main [README.md](../README.md) for guidelines.

