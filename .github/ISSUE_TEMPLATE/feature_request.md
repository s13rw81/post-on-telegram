---
name: Feature Request
description: Suggest an idea or enhancement for post-on-telegram
title: "[FEATURE] "
labels: ["enhancement"]
body:
  - type: textarea
    id: description
    attributes:
      label: Feature description
      description: What would you like to see added or changed?
    validations:
      required: true
  - type: textarea
    id: motivation
    attributes:
      label: Motivation / Use case
      description: Why is this needed and who benefits from it?
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Considered alternatives
      description: Any alternative solutions or workarounds you considered?
    validations:
      required: false
