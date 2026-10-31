<h1 align="center">DataWatch</h1>

DataWatch est une application web de surveillance de sources publiques. Elle permet de repérer des mentions liées à une entreprise ou à un individu à partir de mots-clés, d’adresses e-mail ou de domaines.

Les détections apparaissent dans une interface de suivi avec des alertes et un historique des résultats. Les sources et les règles de surveillance sont configurables depuis l’application.

Le projet utilise Angular pour l’interface, Python pour le back-end et des scripts Bash pour la compilation et le lancement. Les données sont conservées dans une base SQLite locale.

## Installation

### Prérequis

- Git
- Node.js 24 avec npm
- Python 3.12
- Bash

### Récupérer le projet

Depuis le dossier dans lequel tu souhaites installer le projet :

    git clone https://github.com/Shunthail/DataWatch.git
    cd DataWatch

### Compiler et lancer l’application

    bash scripts/build.sh
    bash scripts/start.sh

L’application est ensuite accessible à l’adresse suivante :

http://127.0.0.1:8010

Le back-end utilise uniquement la bibliothèque standard de Python. Aucun paquet Python supplémentaire n’est nécessaire.

### Configurer la surveillance

Au premier lancement, aucune source ni règle n’est préconfigurée.

Ajoute des sources publiques au format RSS, JSON ou texte depuis l’interface. Configure ensuite les mots-clés, les adresses e-mail ou les domaines à surveiller.

Les sources actives sont vérifiées automatiquement toutes les cinq minutes. Les nouvelles détections sont remontées dans l’interface sans rechargement de la page.

### Développement

Pour lancer le back-end et le serveur de développement Angular :

    bash scripts/dev.sh

L’interface de développement est accessible sur http://127.0.0.1:4210.

### Vérifications

Pour exécuter les tests du back-end, vérifier les scripts Bash et compiler l’interface :

    bash scripts/check.sh

## À propos du projet

DataWatch est un projet réalisé avec un groupe d’amis de l’école. Je me suis occupé du back-end et de la sécurité de l’application.

Pour préserver mon anonymat et celui des autres participants, j’ai adapté cette version publique en retirant les informations personnelles présentes dans le projet, notamment les noms, les prénoms et les coordonnées.

Ce dépôt accompagne la présentation de mes compétences sur [shunthail.fr](https://shunthail.fr). Il s’adresse notamment aux recruteurs qui souhaitent consulter mon travail et explorer le code sans avoir à me contacter au préalable.

## Réutilisation et contact

Vous pouvez utiliser le code ou vous inspirer du projet sans me demander d’autorisation. Un message reste toujours apprécié si ce travail vous aide à lancer un projet ou à développer une idée.

Si vous avez une question ou besoin d’aide, vous pouvez me contacter sur Discord : **shunthail**.
