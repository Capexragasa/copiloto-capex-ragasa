# Copiloto CAPEX - Ragasa

Aplicación nueva e independiente del Roadmap/Expediente CAPEX anterior.

## Qué incluye esta versión

- Dashboard ejecutivo de proyectos.
- Expediente con seis módulos CAPEX.
- Memoria local SQLite para pruebas.
- Conexión opcional a Firestore para memoria compartida.
- Generación automática de contexto para analizar cada módulo con Microsoft Copilot.
- Registro de respuestas de Copilot dentro del expediente.
- Historial de cambios por proyecto.
- Respaldo y restauración mediante archivos JSON.
- Archivo de proyectos terminados.

## Ejecutar en una computadora

1. Instala Python 3.11 o superior.
2. Abre una terminal dentro de esta carpeta.
3. Ejecuta:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

4. La aplicación se abrirá en `http://localhost:8501`.

En esta modalidad utiliza una base SQLite dentro de `data/`. Sirve para probar,
pero no es memoria compartida y no debe utilizarse como almacenamiento definitivo
en Streamlit Community Cloud.

## Publicar en Streamlit Community Cloud

1. Crea un repositorio privado nuevo en GitHub.
2. Sube el contenido de esta carpeta.
3. En Streamlit Community Cloud crea una aplicación desde ese repositorio.
4. Selecciona `app.py` como archivo principal.
5. Configura la aplicación como privada e invita únicamente a los correos autorizados.

## Activar la memoria compartida con Firestore

1. Crea un proyecto gratuito en Firebase.
2. Activa Firestore en modo producción.
3. Genera una cuenta de servicio para el servidor.
4. Abre `.streamlit/secrets.example.toml` y úsalo como guía.
5. Copia los valores reales en **Settings > Secrets** de la aplicación desplegada.

No subas `secrets.toml`, llaves privadas ni contraseñas a GitHub. El archivo
`.gitignore` ya excluye los secretos y la base de datos local.

Cuando las credenciales de Firestore están completas, la aplicación cambia
automáticamente de **Memoria local de prueba** a **Memoria compartida activa**.

## Cómo trabaja con Copilot sin API

En cada módulo existe la sección **Analizar con Copilot**:

1. La aplicación prepara un prompt con la memoria completa del expediente.
2. El usuario copia o descarga el prompt y lo envía a Microsoft Copilot.
3. La respuesta se pega de regreso en la aplicación.
4. El resultado queda guardado en la memoria e historial del proyecto.

Este flujo no utiliza tokens de OpenAI o Gemini y no expone llaves de IA.

## Respaldo y archivo

En la pestaña **Archivo** puede descargarse el expediente completo en JSON.
Ese archivo puede guardarse en la carpeta corporativa y restaurarse desde el
menú **Restaurar respaldo**.

La eliminación/depuración permanente no está activada en esta primera versión
para evitar pérdidas accidentales durante el piloto.
