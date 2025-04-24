## 📦 Acción para Combinar PRs de Dependabot

Versión estable de la acción de GitHub que automatiza la combinación de múltiples Pull Requests (PRs) generadas por Dependabot en una sola PR consolidada. Esto facilita la gestión de actualizaciones de dependencias y mantiene un historial de cambios más limpio.

    ✅ Características principales
    🔍 Filtra y procesa únicamente las PRs abiertas creadas por dependabot[bot].
    🔀 Realiza cherry-pick de los commits de cada PR en una nueva rama combinada.
    🧪 Omite automáticamente las PRs que ya han sido aplicadas o que no contienen cambios efectivos.
    📤 Crea una nueva PR con todas las actualizaciones combinadas, basada en la rama especificada.
    📝 Genera un archivo JSON con el resumen de las PRs combinadas, omitidas y fallidas.

⚙️ Variables de entorno requeridas:

    GITHUB_TOKEN: Token de autenticación de GitHub.
    GITHUB_REPOSITORY: Repositorio en formato usuario/repositorio.
    BASE_BRANCH: Rama base para combinar las PRs (por defecto: master).
    COMBINE_BRANCH: Nombre de la nueva rama combinada (por defecto: combine-dependabot).
    PR_USER: Usuario de las ramas de Dependabot (por defecto: dependabot[bot]).
    OUTPUT_JSON: (Opcional) Archivo de salida JSON (por defecto: combined.json).

🧪 Ejemplo de uso:

    on:
    workflow_dispatch:

    jobs:
        combine:
            runs-on: ubuntu-latest
            steps:
              - name: Clonar repositorio
                  uses: actions/checkout@v3
  
              - name: Ejecutar acción de combinación
                  uses: clhore/combine-dependabot-pull-requests@v1
                  with:
                  github_token: ${{ secrets.GITHUB_TOKEN }}
                  base_branch: main
                  combine_branch: combine-dependabot
                  pr_user: dependabot[bot]
                  output_json: combined.json