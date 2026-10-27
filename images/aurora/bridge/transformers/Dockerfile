# SC-2708: el build del tag mutable de semitechnologies (digest 75359f8b, 23-09)
# deja /app/models/model/model.safetensors en 0600 root y el despliegue de Aurora
# corre como uid 1000 → el vectorizer no puede abrir el modelo y cae en bucle.
# Capa única de permisos; sin cambio de contenido.
FROM cr.weaviate.io/semitechnologies/transformers-inference:sentence-transformers-all-MiniLM-L6-v2
USER root
RUN chmod -R a+rX /app/models /app/nltk_data
USER 1000
