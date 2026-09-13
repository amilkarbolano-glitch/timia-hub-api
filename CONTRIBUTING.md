# Flujo de trabajo (git flow simplificado)

```
main     ← estable: lo que está desplegado. Solo recibe merges desde develop (PR).
develop  ← integración: se prueba desplegado (Docker) antes de pasar a main.
feature/<tema>   ← nuevas funcionalidades, salen de develop y vuelven a develop por PR
fix/<tema>       ← correcciones, salen de develop (o de main si es hotfix) y vuelven por PR
```

1. `git checkout develop && git pull`
2. `git checkout -b feature/roles-cliente`
3. commits → `git push -u origin feature/roles-cliente` → PR hacia **develop**
4. Probar develop desplegado (`docker compose up -d --build` en la rama) → PR develop → **main**

Convención de commits: `feat: …`, `fix: …`, `chore: …`, `docs: …`.
