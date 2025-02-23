"""A class to encapsulate ACBF XML data."""
# Copyright 2012-2014 ComicTagger Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import datetime
import logging
import xml.etree.ElementTree as ET
from typing import Any
from typing import TYPE_CHECKING

from comicapi import utils
from comicapi._url import parse_url as parse_url
from comicapi.genericmetadata import GenericMetadata
from comicapi.tags import Tag

if TYPE_CHECKING:
    from comicapi.archivers import Archiver

logger = logging.getLogger(__name__)

ADDITIONAL_CREDITS = [
    'plot',
    'story',
    'interviewer',
    'illustrator',
    'layouts',
    'embellisher',
    'ink assists',
    'color separations',
    'color assists',
    'color flats',
    'digital art technician',
    'gray tone',
    'consulting editor',
    'assistant editor',
    'associate editor',
    'group editor',
    'senior editor',
    'managing editor',
    'collection editor',
    'production',
    'designer',
    'logo design',
    'supervising editor',
    'executive editor',
    'editor in chief',
    'president',
    'publisher',
    'chief creative officer',
    'executive producer',
    'other',
]

METRON_SOURCE_NAME: list[str] = [
    'AniList',
    'Comic Vine',
    'Grand Comics Database',
    'Kitsu',
    'MangaDex',
    'MangaUpdates',
    'Metron',
    'MyAnimeList',
    'League of Comic Geeks',
]


class MetronInfo(Tag):
    enabled = True

    id = 'metroninfo'

    def __init__(self, version: str) -> None:
        super().__init__(version)

        self.file = 'MetronInfo.xml'
        self.supported_attributes = {
            'series',
            'series_aliases',
            'issue',
            'issue_count',
            'title',
            'title_aliases',  # Collection title?
            'volume',
            'volume_count',
            'genres',
            'description',  # Summary
            'notes',
            'format',  # https://metron-project.github.io/docs/metroninfo/documentation#series -> Format
            'publisher',
            'imprint',
            'day',
            'month',
            'year',
            'language',
            'web_links',
            'manga',
            'maturity_rating',  # https://metron-project.github.io/docs/metroninfo/ratings
            'tags',
            'story_arcs',
            'characters',
            'teams',
            'locations',
            'credits',
            'credits.person',
            'credits.role',
            'data_origin',
            'price',
            'issue_id',
            'series_id',
            'identifier',  # GTIN -> ISBN, UPC
        }

    def supports_credit_role(self, role: str) -> bool:
        return role.casefold() in self._get_parseable_credits()

    def supports_tags(self, archive: Archiver) -> bool:
        return archive.supports_files()

    def has_tags(self, archive: Archiver) -> bool:
        try:  # read_file can cause an exception
            return (
                self.supports_tags(archive)
                and self.file in archive.get_filename_list()
                and self._validate_bytes(archive.read_file(self.file))
            )
        except Exception:
            return False

    def remove_tags(self, archive: Archiver) -> bool:
        return self.has_tags(archive) and archive.remove_file(self.file)

    def read_tags(self, archive: Archiver) -> GenericMetadata:
        if self.has_tags(archive):
            try:  # read_file can cause an exception
                metadata = archive.read_file(self.file) or b''
                if self._validate_bytes(metadata):
                    return self._metadata_from_bytes(metadata)
            except Exception:
                ...
        return GenericMetadata()

    def read_raw_tags(self, archive: Archiver) -> str:
        try:  # read_file can cause an exception
            if self.has_tags(archive):
                b = archive.read_file(self.file)
                # ET.fromstring is used as xml can declare the encoding
                return ET.tostring(ET.fromstring(b), encoding='unicode', xml_declaration=True)
        except Exception:
            ...
        return ''

    def write_tags(self, metadata: GenericMetadata, archive: Archiver) -> bool:
        if self.supports_tags(archive):
            xml = b''
            try:  # read_file can cause an exception
                if self.has_tags(archive):
                    xml = archive.read_file(self.file)
                return archive.write_file(self.file, self._bytes_from_metadata(metadata, xml))
            except Exception as e:
                logger.warning(f"Failed to write tag for MetronInfo: {e}")
        else:
            logger.warning(f"Archive ({archive.name()}) does not support {self.name()} metadata")
        return False

    def name(self) -> str:
        return 'Metron Info'

    @classmethod
    def _get_parseable_credits(cls) -> list[str]:
        parsable_credits: list[str] = []
        parsable_credits.extend(GenericMetadata.writer_synonyms)
        parsable_credits.extend(GenericMetadata.penciller_synonyms)
        parsable_credits.extend(GenericMetadata.inker_synonyms)
        parsable_credits.extend(GenericMetadata.colorist_synonyms)
        parsable_credits.extend(GenericMetadata.letterer_synonyms)
        parsable_credits.extend(GenericMetadata.cover_synonyms)
        parsable_credits.extend(GenericMetadata.editor_synonyms)
        parsable_credits.extend(GenericMetadata.translator_synonyms)
        parsable_credits.extend(ADDITIONAL_CREDITS)
        return parsable_credits

    def _metadata_from_bytes(self, string: bytes) -> GenericMetadata:
        root = ET.fromstring(string)
        return self._convert_xml_to_metadata(root)

    def _bytes_from_metadata(self, metadata: GenericMetadata, xml: bytes = b'') -> bytes:
        root = self._convert_metadata_to_xml(metadata, xml)
        return ET.tostring(root, encoding='utf-8', xml_declaration=True)

    def _convert_metadata_to_xml(self, metadata: GenericMetadata, xml: bytes = b'') -> ET.Element:
        def add_element(element: ET.Element, sub_element: str, text: str = '', attribs: dict[str, str] | None = None) -> None:
            if not isinstance(element, ET.Element):
                raise Exception('add_element: Not an ET.Element: %s', element)

            attribs = attribs or {}

            new_element = ET.SubElement(element, sub_element)

            if text:
                new_element.text = str(text)

            for k, v in attribs.items():
                new_element.attrib[k] = v

        def add_path(path: str) -> ET.Element:
            path_list: list[str] = path.split('/')
            test_path: str = ''

            for i, p in enumerate(path_list):
                test_path = '/'.join(path_list[:i + 1])

                if root.find(test_path) is None:
                    if i == 0:
                        add_element(root, p)
                    else:
                        *element_path_parts, element_name = test_path.split('/')
                        element_path = '/'.join(element_path_parts)
                        add_root = root.find(element_path)
                        if add_root is None:
                            raise Exception('add_path: Failed to find XML path element: %s', add_root)
                        else:
                            add_element(add_root, p)

            ele = root.find(path)
            if ele is None:
                raise Exception('add_path: Failed to create XML path element: %s', path)
            else:
                return ele

        def get_or_create_element(tag: str) -> ET.Element:
            element = root.find(tag)
            if element is None:
                element = add_path(tag)
            return element

        def remove_attribs(ele: ET.Element) -> ET.Element:
            ele.attrib.clear()
            return ele

        def modify_element(path: str, value: Any, attribs: dict[str, str] | None = None, clear_attribs: bool = False) -> None:
            attribs = attribs or {}

            # Split the path into parent and element name
            *element_path_parts, element_name = path.split('/')
            element_path = '/'.join(element_path_parts)

            element_parent = get_or_create_element(element_path)

            element = root.find(path)
            if element is None:
                try:
                    element = ET.SubElement(element_parent, element_name)
                except Exception as e:
                    logger.warning(f'Failed to modify XML element: {element_path}, {element_name}. Error: {e}')
                    return

            if clear_attribs:
                element = remove_attribs(element)

            element.text = str(value)
            for k, v in attribs.items():
                element.attrib[k] = v

        def clear_element(full_ele: str) -> None:
            element_path, _, element_name = full_ele.rpartition('/')
            element_parent = root.find(element_path)
            if element_parent is not None:
                for e in element_parent.findall(element_name):
                    element_parent.remove(e)

        def add_credit(creator: str, roles: list[str]) -> None:
            if creator:
                ele_credit = ET.SubElement(metron_credits, 'Credit')
                add_element(ele_credit, 'Creator', creator)

                if len(roles) > 0:
                    ele_roles = ET.SubElement(ele_credit, 'Roles')
                    for role in roles:
                        ele_role = ET.SubElement(ele_roles, 'Role')
                        ele_role.text = role
                        # if role_id:
                        # ele_role.attrib['id'] = role_id

        # xml is empty bytes or has the read metroninfo xml
        # shorthand for the metadata
        md = metadata

        if xml:
            root = ET.fromstring(xml)
        else:
            root = ET.Element('MetronInfo')
            root.attrib['xmlns:xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'
            root.attrib['xsi:noNamespaceSchemaLocation'] = 'MetronInfo.xsd'

        metron_ids = get_or_create_element('IDS')
        metron_number = get_or_create_element('Number')
        metron_series = get_or_create_element('Series')
        metron_stories = get_or_create_element('Stories')
        metron_title = get_or_create_element('CollectionTitle')
        metron_summary = get_or_create_element('Summary')
        metron_notes = get_or_create_element('Notes')
        metron_prices = get_or_create_element('Prices')
        metron_gtin = get_or_create_element('GTIN')
        metron_genres = get_or_create_element('Genres')
        metron_age_rating = get_or_create_element('AgeRating')
        metron_tags = get_or_create_element('Tags')
        metron_arcs = get_or_create_element('Arcs')
        metron_characters = get_or_create_element('Characters')
        metron_teams = get_or_create_element('Teams')
        # metron_unis = get_or_create_element('Universes')
        metron_locs = get_or_create_element('Locations')
        # metron_reprints = get_or_create_element('Reprints')
        metron_publisher = get_or_create_element('Publisher')
        metron_cover_date = get_or_create_element('CoverDate')
        metron_urls = get_or_create_element('URLs')
        metron_credits = get_or_create_element('Credits')
        metron_modified = get_or_create_element('LastModified')

        # Create a dict for each person so multiple roles can be added
        creators: dict[str, tuple[str, list[str]]] = {}  # casefold_name: (Name, list[role])
        for credit in md.credits:
            creator_folded: str = credit.person.replace(' ', '_').casefold()
            credit_role: str = ''

            if credit.role.casefold() in GenericMetadata.writer_synonyms:
                credit_role = 'Writer'
            elif credit.role.casefold() in GenericMetadata.penciller_synonyms:
                credit_role = 'Penciller'
            elif credit.role.casefold() in GenericMetadata.inker_synonyms:
                credit_role = 'Inker'
            elif credit.role.casefold() in GenericMetadata.colorist_synonyms:
                credit_role = 'Colorist'
            elif credit.role.casefold() in GenericMetadata.letterer_synonyms:
                credit_role = 'Letterer'
            elif credit.role.casefold() in GenericMetadata.cover_synonyms:
                credit_role = 'Cover'
            elif credit.role.casefold() in GenericMetadata.editor_synonyms:
                credit_role = 'Editor'
            elif credit.role.casefold() in ADDITIONAL_CREDITS:
                credit_role = credit.role
            else:
                credit_role = 'Other'

            creators.setdefault(creator_folded, (credit.person, []))[1].append(credit_role)

        # Add credits
        # Clear for now but later may preserve IDs
        metron_credits.clear()
        for creator in creators.values():
            add_credit(creator[0], creator[1])

        metron_series.clear()
        if md.series:
            if md.series_id is not None:
                metron_series.attrib['id'] = md.series_id

            add_element(metron_series, 'Name', md.series)

            if md.volume:
                add_element(metron_series, 'Volume', str(md.volume))

            if md.format:
                # 'Annual', 'Digital Chapter', 'Graphic Novel', 'Hardcover', 'Limited Series', 'Omnibus', 'One-Shot',
                # 'Single Issue', 'Trade Paperback'
                format_dict = {
                    'annual': 'Annual', 'digital chapter': 'Digital Chapter', 'graphic novel': 'Graphic Novel',
                    'hardcover': 'Hardcover', 'limited series': 'Limited Series', 'omnibus': 'Omnibus', 'trade paperback': 'Trade Paperback',
                    'oneshot': 'One-Shot', 'single issue': 'Single Issue',
                }

                format_tpb = ['trade paperback', 'collected edition', 'tpb', 'anthology', 'trade paper back']
                format_one_shot = ['oneshot', 'one-shot', 'one shot', '1-shot', '1 shot', '1shot']

                if md.format.lower().casefold() in format_tpb:
                    md.format = format_tpb[0]
                elif md.format.lower().casefold() in format_one_shot:
                    md.format = format_one_shot[0]

                md.format = format_dict.get(md.format.lower().casefold(), 'Single Issue')

                add_element(metron_series, 'Format', md.format)

            # Start Year?

            if md.issue_count:
                add_element(metron_series, 'IssueCount', str(md.issue_count))

            if md.volume_count:
                add_element(metron_series, 'VolumeCount', str(md.volume_count))

            if md.series_aliases:
                series_alts = ET.SubElement(metron_series, 'AlternativeNames')

                for series_alt in md.series_aliases:
                    add_element(series_alts, 'AlternativeName', series_alt)

        metron_number.clear()
        if md.issue:
            metron_number.text = md.issue

        metron_stories.clear()
        metron_title.clear()
        if md.title:
            # If the md.format is 'Trade Paperback' (already processed), set the CollectionTitle. Otherwise, use stories
            # TODO Put TPB title in both?
            if md.format == 'Trade Paperback':
                metron_title.text = md.title
            else:
                split_titles = md.title.split(';')
                for title in split_titles:
                    add_element(metron_stories, 'Story', title.strip())

        if md.manga is not None and md.manga.casefold().startswith('yes'):
            md.genres.add('Manga')

        metron_genres.clear()
        for g in md.genres:
            add_element(metron_genres, 'Genre', g.capitalize())

        metron_summary.clear()
        if md.description:
            metron_summary.text = md.description

        metron_urls.clear()
        if md.web_links:
            for web in md.web_links:
                add_element(metron_urls, 'URL', web)

        metron_age_rating.clear()
        if md.maturity_rating:
            # Unknown, Everyone, Teen, Teen Plus, Mature, Explicit, Adult
            mature_dict = {
                'unknown': 'Unknown', 'everyone': 'Everyone', 'teen': 'Teen', 'teen plus': 'Teen Plus',
                'mature': 'Mature', 'explicit': 'Explicit', 'adult': 'Adult',
            }

            # https://metron-project.github.io/docs/metroninfo/ratings
            mature_everyone = ['everyone', 'G', 'all', 'all ages', 'a', 't']
            mature_teen = ['teen', 'teenager', '13+', 'T+', 'PG', 'PSR']
            mature_teenplus = ['teen plus', 'teenager plus', '15+', 'parental advisory', 'PG+', 'PSR+', 'ma15+']
            mature_mature = ['mature', '17+', 'explicit content', 'm', 'mature 17+']  # Why 'Explicit Content' is mature, don't know
            mature_explicit = ['explicit', 'R']
            mature_adult = ['adult', 'adults only', 'adults only 18+', '18+', 'R18+', 'R+']

            if md.maturity_rating.lower().casefold() in mature_everyone:
                md.maturity_rating = mature_everyone[0]
            elif md.maturity_rating.lower().casefold() in mature_teen:
                md.maturity_rating = mature_teen[0]
            elif md.maturity_rating.lower().casefold() in mature_teenplus:
                md.maturity_rating = mature_teenplus[0]
            elif md.maturity_rating.lower().casefold() in mature_mature:
                md.maturity_rating = mature_mature[0]
            elif md.maturity_rating.lower().casefold() in mature_explicit:
                md.maturity_rating = mature_explicit[0]
            elif md.maturity_rating.lower().casefold() in mature_adult:
                md.maturity_rating = mature_adult[0]

            md.maturity_rating = mature_dict.get(md.maturity_rating.lower().casefold(), 'Unknown')

            metron_age_rating.text = md.maturity_rating

        metron_tags.clear()
        if md.tags:
            for tag in md.tags:
                add_element(metron_tags, 'Tag', tag)

        metron_characters.clear()
        if md.characters:
            for c in md.characters:
                add_element(metron_characters, 'Character', c)

        metron_teams.clear()
        if md.teams:
            for team in md.teams:
                add_element(metron_teams, 'Team', team)

        metron_locs.clear()
        if md.locations:
            for loc in md.locations:
                add_element(metron_locs, 'Location', loc)

        metron_arcs.clear()
        if md.story_arcs:
            for arc in md.story_arcs:
                arc_element = ET.SubElement(metron_arcs, 'Arc')
                add_element(arc_element, 'Name', arc)

        # Will preserve IDs of sources
        if md.issue_id:
            # Sources: AniList, Comic Vine, Grand Comics Database, Kitsu, MangaDex, MangaUpdates, Metron, MyAnimeList, League of Comic Geeks
            found = False
            for current_id in metron_ids:
                if current_id.attrib['source'] == md.data_origin.name:
                    current_id.text = md.issue_id
                    current_id.attrib['primary'] = 'true'
                    found = True
                    break
            if not found:
                add_element(metron_ids, 'ID', md.issue_id, {'source': md.data_origin.name, 'primary': 'true'})

        metron_publisher.clear()
        if md.publisher:
            add_element(metron_publisher, 'Name', md.publisher)
            if md.imprint:
                add_element(metron_publisher, 'Imprint', md.imprint)

        metron_gtin.clear()
        # Assume ISBN
        if md.identifier:
            add_element(metron_gtin, 'ISBN', md.identifier)

        metron_cover_date.clear()
        if md.year:
            day = md.day or 1
            month = md.month or 1
            year = md.year
            if int(year) < 50:
                # Presume 20xx
                year = 2000 + year
            elif year < 100:
                year = 1900 + year

            pub_date = f'{year:04}-{month:02}-{day:02}'
            metron_cover_date.text = pub_date

        metron_notes.clear()
        if md.notes:
            metron_notes.text = md.notes

        metron_prices.clear()
        if md.price:
            # Assume price is $
            add_element(metron_prices, 'Price', str(md.price), {'country': 'US'})

        metron_modified.text = datetime.datetime.now().isoformat()

        # MangaVolume
        # StoreDate
        # PageCount
        # Universes
        # Reprints

        ET.indent(root)

        return root

    def _convert_xml_to_metadata(self, root: ET.Element) -> GenericMetadata:

        def get_text(name: str, element: ET.Element | None = None) -> str | None:
            if element is None:
                tag = root.find('.//' + name)
            else:
                tag = element.find('.//' + name)

            if tag is None:
                return None

            return tag.text

        def get_element(name: str, element: ET.Element | None = None) -> ET.Element | None:
            if element is None:
                tag = root.find('.//' + name)
            else:
                tag = element.find('.//' + name)

            if tag is None:
                return None

            return tag

        if root.tag != 'MetronInfo':
            raise Exception('Not a MetronInfo file')

        md = GenericMetadata()

        # md.issue_id =  # No way to tie current selected talker to IDs?

        # Set the collection title first and then overwrite is there is also "Stories"
        m_title: str | None = utils.xlate(get_text('CollectionTitle'))

        m_series: ET.Element | None = get_element('Series')
        m_stories: ET.Element | None = get_element('Stories')
        m_genres: ET.Element | None = get_element('Genres')
        m_arcs: ET.Element | None = get_element('Arcs')
        m_publisher: ET.Element | None = get_element('Publisher')
        m_urls: ET.Element | None = get_element('URLs')
        m_characters: ET.Element | None = get_element('Characters')
        m_teams: ET.Element | None = get_element('Teams')
        m_locations: ET.Element | None = get_element('Locations')
        m_tags: ET.Element | None = get_element('Tags')
        m_prices: ET.Element | None = get_element('Prices')
        m_gtin: ET.Element | None = get_element('GTIN')
        m_credits: ET.Element | None = get_element('Credits')

        if m_title is None and m_stories is not None:
            stories: list[str] = []
            for story in m_stories:
                if story.text is not None:
                    stories.append(story.text)
            m_title = ';'.join(stories)

        md.series = utils.xlate(get_text('Name', m_series))
        md.issue = utils.xlate(get_text('Number'))
        md.issue_count = utils.xlate(get_text('IssueCount', m_series))
        md.title = m_title
        md.volume = utils.xlate(get_text('Volume', m_series))

        if m_genres is not None:
            genres = set()
            for genre in m_genres:
                genres.add(genre.text)
            md.genres = genres

        md.description = utils.xlate(get_text('Summary'))
        md.notes = utils.xlate(get_text('Notes'))

        if m_arcs is not None:
            arcs: list[str] = []
            for arc in m_arcs:
                arc_text = get_text('Name', arc)
                if arc_text is not None:
                    arcs.append(arc_text)
            md.story_arcs = arcs

        md.publisher = utils.xlate(get_text('Name', m_publisher))
        md.imprint = utils.xlate(get_text('Imprint', m_publisher))

        cover_date = utils.parse_date_str(utils.xlate(get_text('CoverDate')))
        if cover_date[0] is not None:
            md.day = utils.xlate_int(cover_date[0])
        if cover_date[1] is not None:
            md.month = utils.xlate_int(cover_date[1])
        if cover_date[2] is not None:
            md.year = utils.xlate_int(cover_date[2])

        if m_gtin is not None:
            # Prefer ISBN
            for ident in m_gtin:
                if ident.tag == 'ISBN':
                    md.identifier = ident.text
                elif md.identifier is None:
                    md.identifier = ident.text

        if m_prices is not None:
            if len(m_prices) > 1:
                # Prefer US price?
                for price in m_prices:
                    if price.attrib['country'] == 'US':
                        md.price = price.text

            # Only 1 price or none US
            if md.price is None and len(m_prices) == 1:
                md.price = m_prices[0].text

        if m_series is not None:
            md.language = m_series.attrib.get('lang')

        if m_urls is not None:
            urls = []
            for url in m_urls:
                if url.text is not None:
                    urls.append(url.text)
            md.web_links = utils.split_urls(' '.join(urls))

        md.format = utils.xlate(get_text('Format', m_series))
        md.maturity_rating = utils.xlate(get_text('AgeRating'))
        md.page_count = utils.xlate_int(get_text('PageCount'))

        if m_characters is not None:
            characters = set()
            for character in m_characters:
                characters.add(character.text)
            md.characters = characters

        if m_teams is not None:
            teams = set()
            for team in m_teams:
                teams.add(team.text)
            md.teams = teams

        if m_locations is not None:
            locations = set()
            for location in m_locations:
                locations.add(location.text)
            md.locations = locations

        if m_tags is not None:
            tags = set()
            for tag in m_tags:
                tags.add(tag.text)
            md.tags = tags

        # Now extract the credit info
        if m_credits is not None:
            for credit in m_credits:
                creator = utils.xlate(get_text('Creator', credit))
                if creator is not None:
                    roles = get_element('Roles', credit)
                    if roles is not None:
                        for role in roles:
                            md.add_credit(creator, role.text)

        md.is_empty = False

        return md

    def _validate_bytes(self, string: bytes) -> bool:
        """Verify that the string actually contains ACBF data in XML format."""
        try:
            root = ET.fromstring(string)
            if root.tag != 'MetronInfo':
                return False
        except ET.ParseError:
            return False

        return True
