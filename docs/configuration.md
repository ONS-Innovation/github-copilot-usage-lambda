# Configuration

The Copilot lambda uses a local configuration file to manage its settings, located within `./config/config.json`.

## `config.json`

The `config.json` file contains the following:

```json
{
  "features": {
    "show_log_locally": false,
    "write_data_locally": false
  },
}
```

### `features` Section

This section contains feature flags that control which of the tool's features are enabled or disabled.

#### `show_log_locally`

If set to `true`, the tool will output logs to the terminal.

When deploying to AWS, this should be set to `false` to avoid files being written to the local filesystem.

#### `write_data_locally`

If set to `true`, the tool will skip writing to S3 and instead write data for copilot teams, historic usage, and teams history to `local_data`.

**When deploying to AWS, this must be set to `false` to ensure the tool writes to AWS.**

When debugging locally, you can set this to `true` to use the local configuration file. This is useful if you need to see the logs locally, without affecting the cloud deployment.

### Example During Local Testing

When testing locally, you might set the `config.json` file as follows:

```json
{
  "features": {
    "show_log_locally": true,
    "write_data_locally": true
  },
}
```

### Example On AWS

When deploying to AWS, the `config.json` file should be set as follows:

```json
{
  "features": {
    "show_log_locally": false,
    "write_data_locally": false
  },
}
```

This configuration ensures that the tool does not log or write data locally.

**It is essential that `write_data_locally` is set to `false` when deploying to AWS.**
