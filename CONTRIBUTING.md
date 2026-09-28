# Flujo de trabajo

```
main             ← desplegada en AWS: cada merge a main dispara CodePipeline (pruebas → imagen → ECS)
feature/<tema>   ← nuevas funcionalidades, salen de main y vuelven por PR
fix/<tema>       ← correcciones, salen de main y vuelven por PR
```

1. `git checkout main && git pull`
2. `git checkout -b feature/roles-cliente`
3. commits → `git push -u origin feature/roles-cliente` → PR hacia **main** (GitHub Actions corre las pruebas)
4. Probar en local (`docker compose up -d --build`) antes de pedir revisión
5. Merge del PR → despliegue automático (ver `INFRA-AWS.md`)

Convención de commits: `feat: …`, `fix: …`, `chore: …`, `docs: …`.
