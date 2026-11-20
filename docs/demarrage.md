# Démarrer Odoo dans Codespaces

Ouvrir un Codespace depuis le dépôt. Si Codespaces était déjà ouvert avant
l'ajout de la configuration, exécuter **Codespaces: Rebuild Container**.

Initialiser une base de développement neuve et installer le module.

```bash
docker compose run --rm odoo odoo -d insea_erp \
  -i insea_hr_leave_custom --without-demo=all --stop-after-init
docker compose up -d
```

Ouvrir le port **8069** dans l’onglet **Ports** et conserver sa visibilité
privée. Utiliser `admin` comme identifiant et mot de passe de la base locale
à la première connexion, puis changer le mot de passe. La base et les fichiers
Odoo restent dans les volumes Docker du Codespace.

Pour mettre à jour le module après une modification du code ou des données.

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d insea_erp \
  -u insea_hr_leave_custom --stop-after-init
docker compose up -d
```

## Vérifier le passage de relais

Créer les comptes de test et associer le collaborateur à une fiche employé
et à un approbateur Congés. Depuis le compte collaborateur, enregistrer une
**Autorisation de sortie INSEA**. Coche **Heures**, choisis une plage travaillée de deux heures et renseigne le motif. Le formulaire peut se rouvrir depuis **Mes congés**. Rouvrir la demande
et vérifier qu’elle est en brouillon. Utiliser le bouton standard **Confirmer**
pour passer à l’état en attente d’approbation.
