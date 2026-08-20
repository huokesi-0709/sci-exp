# Radxa 本地推理可执行文件

将与 Radxa CPU 架构和系统匹配的 `llama-server` 放在本目录，复制到设备后执行：

```bash
chmod +x /home/radxa/sci-exp/bin/llama-server
MODEL_PATH=/home/radxa/sci-exp/models/your-model.gguf \
  bash /home/radxa/sci-exp/scripts/start_llama_server.sh
```

二进制文件较大且与具体 Radxa 型号/架构有关，因此当前没有伪装成通用文件。其版本、
编译参数和 SHA-256 应记录进 `manifests/models.example.json` 的正式副本。
