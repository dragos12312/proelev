import { describe, it, expect, beforeEach } from 'vitest'
import { homeworks, addHomework, updateHomework, deleteHomework } from './homeworks.js'

beforeEach(() => {
  homeworks.value = [
    { id: 1, title: 'Înmulțiri', subject: 'Matematică', assignedClass: '4A', dueDate: '2026-03-25', submitted: 5, total: 20, description: 'Test', file: null, fileName: '' },
    { id: 2, title: 'Substantivul', subject: 'Limba Română', assignedClass: '4A', dueDate: '2026-03-26', submitted: 12, total: 20, description: 'Test', file: null, fileName: '' },
  ]
})

describe('addHomework', () => {
  it('adds a new homework to the list', () => {
    addHomework({ title: 'Test', subject: 'Istorie', assignedClass: '4B', dueDate: '2026-04-01', description: 'desc', file: null, fileName: '' })
    expect(homeworks.value.length).toBe(3)
  })

  it('assigns a unique id', () => {
    addHomework({ title: 'Test', subject: 'Istorie', assignedClass: '4B', dueDate: '2026-04-01', description: 'desc', file: null, fileName: '' })
    expect(homeworks.value[2].id).toBe(3)
  })

  it('saves the correct title', () => {
    addHomework({ title: 'Nou', subject: 'Geografie', assignedClass: '4A', dueDate: '2026-04-02', description: 'desc', file: null, fileName: '' })
    expect(homeworks.value[2].title).toBe('Nou')
  })
})

describe('updateHomework', () => {
  it('updates the title of an existing homework', () => {
    updateHomework(1, { title: 'Modificat', subject: 'Matematică', assignedClass: '4A', dueDate: '2026-03-25', description: 'Test', file: null, fileName: '' })
    expect(homeworks.value[0].title).toBe('Modificat')
  })

  it('does not change other homeworks', () => {
    updateHomework(1, { title: 'Modificat', subject: 'Matematică', assignedClass: '4A', dueDate: '2026-03-25', description: 'Test', file: null, fileName: '' })
    expect(homeworks.value[1].title).toBe('Substantivul')
  })

  it('does nothing if id does not exist', () => {
    updateHomework(99, { title: 'X', subject: 'X', assignedClass: 'X', dueDate: 'X', description: 'X', file: null, fileName: '' })
    expect(homeworks.value.length).toBe(2)
  })
})

describe('deleteHomework', () => {
  it('removes a homework by id', () => {
    deleteHomework(1)
    expect(homeworks.value.length).toBe(1)
  })

  it('removes the correct homework', () => {
    deleteHomework(1)
    expect(homeworks.value[0].id).toBe(2)
  })

  it('does nothing if id does not exist', () => {
    deleteHomework(99)
    expect(homeworks.value.length).toBe(2)
  })
})