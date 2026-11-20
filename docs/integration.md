# Partie A — périmètre et intégration

Le module réutilise les demandes, les employés, les calendriers, les états,
les soumissions, les pièces jointes et les allocations du module
`hr_holidays`. Les types préconfigurés portent la politique INSEA et
commencent dans l’état standard `draft`. Le bouton natif utilise
`action_confirm` pour passer à `confirm`.

## Paramétrage de la démonstration

- Pour un congé annuel, crée et valide une allocation par employé avec le
  plan de cumul **INSEA — 1,5 jour par mois travaillé**. Le plan est
  configuré pour créditer en fin de période. Une allocation ordinaire
  validée peut fournir un solde de départ pour les essais.
- Les congés en jours suivent le calendrier de travail individuel d’Odoo.
  Pour un décès, 2 et 3 jours sont acceptés en attendant une règle de
  distinction entre les situations.
- Le quota de sorties est calculé par employé sur le mois civil de la
  date de sortie. Les états soumis, en seconde approbation et approuvé
  consomment le quota. Les brouillons, refus et annulations en sont exclus.
  Le plafond utilise la durée écoulée de la plage horaire.

## Contrat pour B

- Réutiliser `draft`, `confirm`, `validate1`, `validate`, `refuse`
  et les actions standard. Le type sortie utilise l’approbateur de la
  fiche employé. Les autres types sont préconfigurés en double approbation.
  La maladie d’un jour reste à traiter avec le circuit choisi par le binôme.
- Le champ calculé `insea_needs_attachment` indique si un justificatif
  est exigé. B doit l’exploiter au moment de la validation finale avec les
  pièces jointes standard `supported_attachment_ids`.
- B ajoute les restrictions de modification et de consultation, le motif
  de refus et la notification, ainsi que les adaptations de vues qui
  relèvent du circuit d’approbation.

## Lancer les tests dans un Codespace

```bash
docker compose run --rm odoo odoo -d insea_tests --db-filter='^insea_tests$' \
  -i insea_hr_leave_custom --without-demo=all \
  --test-enable --test-tags=/insea_hr_leave_custom --stop-after-init
```

Sur une base de tests déjà initialisée, utiliser `-u` à la place de `-i`.
