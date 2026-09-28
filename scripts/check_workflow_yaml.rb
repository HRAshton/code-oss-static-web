#!/usr/bin/env ruby
# frozen_string_literal: true

require 'yaml'

Dir['.github/workflows/*.yml'].sort.each do |path|
  begin
    YAML.safe_load(File.read(path), aliases: true)
  rescue Psych::SyntaxError => e
    warn "#{path}: #{e.message}"
    exit 1
  end
end

puts 'workflow YAML syntax: ok'
